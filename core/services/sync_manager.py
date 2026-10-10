# -*- coding: utf-8 -*-
"""云同步服务 —— 「看过的漫画 JM 号」与自有服务器双向合并（对齐手机端 v1.10.0）。

同步服务器（自备，与手机端实现同一协议）：
  GET  /pull?token=T   → {"count":N,"detail":[{id,added_at,last_read_at}...]}
  POST /push?token=T   body {"ids":[...]} → {"ok":true,"received":N,"new":M}

合并语义（本地为权威、幂等可重跑）：
  - 入：服务器有、本地账本无 → 落一张最小账本行（只有 JM 号，元数据留空；
    要看哪本直接搜 JM 号进详情，元数据自然落库）；
  - 出：本地账本全集全量 push（服务器 INSERT OR IGNORE，重复 push 无副作用）；
  - 只有成功同步才写 sync_last_at（自动同步的 6 小时节流依据）。
服务器只存数字 ID + 时间戳，不存任何书名/文本（隐私最小化）。
"""

import time

# 性能：requests 惰性 import（启动省 ~121ms），在 _pull/_push/_friendly_error 内按需加载
from core.models.database import (
    get_all_status_ids,
    get_system_config,
    set_system_config,
    touch_comic_status,
)

# 启动自动同步节流：距上次成功同步超过 6 小时才跑（手动「立即同步」不受限）
AUTO_SYNC_INTERVAL_MS = 6 * 60 * 60 * 1000


class SyncManager:
    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    # ── 配置 ───────────────────────────────────────────────
    def _cfg(self, key: str, default: str = "") -> str:
        return (get_system_config(key) or default).strip()

    def is_enabled(self) -> bool:
        return self._cfg("sync_enabled", "0") == "1"

    def is_configured(self) -> bool:
        url = self._cfg("sync_server_url").rstrip("/")
        token = self._cfg("sync_token")
        return url.startswith("http") and bool(token)

    def status(self) -> dict:
        token = self._cfg("sync_token")
        masked = ("*" * max(0, len(token) - 4) + token[-4:]) if len(token) > 4 else token
        return {
            "enabled": self.is_enabled(),
            "configured": self.is_configured(),
            "server_url": self._cfg("sync_server_url"),
            "token_masked": masked,
            "last_at": int(self._cfg("sync_last_at", "0") or 0),
            "last_result": self._cfg("sync_last_result"),
        }

    # ── 同步入口 ───────────────────────────────────────────
    def sync_now(self) -> dict:
        """立即双向同步。成功返回汇总，失败抛 RuntimeError（中文文案，已写 last_result）。"""
        try:
            result = self._do_sync()
            set_system_config(
                "sync_last_result",
                f"✅ 拉回 {result['pulled']} · 推上 {result['pushed']}"
                f"（服务器新增 {result['new_on_server']}，账本共 {result['server_total']}）",
            )
            return result
        except Exception as e:
            msg = self._friendly_error(e)
            set_system_config("sync_last_result", f"❌ {msg}")
            raise RuntimeError(msg)

    def auto_sync_if_due(self) -> None:
        """启动时静默自动同步：启用 + 配置完整 + 距上次成功 ≥6h 才跑；失败只打日志。"""
        try:
            if not self.is_enabled() or not self.is_configured():
                return
            last = int(self._cfg("sync_last_at", "0") or 0)
            if int(time.time() * 1000) - last < AUTO_SYNC_INTERVAL_MS:
                return
            result = self._do_sync()
            set_system_config(
                "sync_last_result",
                f"✅ 拉回 {result['pulled']} · 推上 {result['pushed']}"
                f"（服务器新增 {result['new_on_server']}，账本共 {result['server_total']}）",
            )
            print(f"[Sync] 启动自动同步完成：{result}")
        except Exception as e:
            print(f"[Sync] 启动自动同步失败（静默忽略）: {e}")

    # ── 核心流程 ───────────────────────────────────────────
    def _do_sync(self) -> dict:
        url = self._cfg("sync_server_url").rstrip("/")
        token = self._cfg("sync_token")
        if not url.startswith("http") or not token:
            raise RuntimeError("未配置服务器地址或密钥（设置 → 书架 → 云同步）")

        # 1) pull：服务器账本全量
        server_rows = self._pull(url, token)

        # 2) 合并入：服务器有、本地账本无 → 落最小账本行（本地已有行绝不动）
        local_ids = set(get_all_status_ids())
        pulled = 0
        for row in server_rows:
            if row["id"] not in local_ids:
                touch_comic_status(row["id"])
                pulled += 1

        # 3) 合并出：账本全集全量 push（服务器幂等）
        push_ids = get_all_status_ids()
        new_on_server = self._push(url, token, push_ids)

        # 4) 记账：成功才写 sync_last_at（自动同步节流依据）
        set_system_config("sync_last_at", str(int(time.time() * 1000)))
        return {
            "pulled": pulled,
            "pushed": len(push_ids),
            "new_on_server": new_on_server,
            "server_total": len(server_rows) + new_on_server,
        }

    # ── HTTP ───────────────────────────────────────────────
    def _pull(self, url: str, token: str) -> list:
        import requests
        resp = requests.get(f"{url}/pull", params={"token": token}, timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(self._http_error(resp.status_code))
        data = resp.json()
        detail = data.get("detail") or []
        out = []
        for item in detail:
            try:
                out.append({
                    "id": int(item.get("id") or 0),
                    "added_at": int(item.get("added_at") or 0),
                    "last_read_at": int(item.get("last_read_at") or 0),
                })
            except (TypeError, ValueError):
                continue
        return [r for r in out if r["id"] > 0]

    def _push(self, url: str, token: str, ids: list) -> int:
        import requests
        resp = requests.post(
            f"{url}/push", params={"token": token}, json={"ids": ids}, timeout=self.timeout
        )
        if resp.status_code != 200:
            raise RuntimeError(self._http_error(resp.status_code))
        data = resp.json()
        try:
            return int(data.get("new") or 0)
        except (TypeError, ValueError):
            return 0

    # ── 错误文案 ───────────────────────────────────────────
    @staticmethod
    def _http_error(code: int) -> str:
        if code == 403:
            return "密钥不对（403）"
        return f"服务器返回 {code}"

    @staticmethod
    def _friendly_error(e: Exception) -> str:
        import requests
        if isinstance(e, RuntimeError):
            return str(e)
        if isinstance(e, requests.exceptions.Timeout):
            return "同步超时：服务器暂时不可达"
        if isinstance(e, requests.exceptions.ConnectionError):
            return "连不上同步服务器（检查网络/地址）"
        return f"同步失败：{e}"