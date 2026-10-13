# -*- coding: utf-8 -*-
"""JM 客户端与 option 配置（自 jm_crawler.py 拆出）。

并发常量、系统代理探测、option 文件生成与合并、客户端复用（keep-alive）。"""

import os
import shutil
import sys
import yaml
from typing import Dict, Optional

from core.models.database import get_system_config

from core.logging_setup import get_logger

log = get_logger("jm_crawler")

# ── 下载并发上限 ──────────────────────────────────────────
# 实测 jmcomic 的真实并发开关是 download.threading.image / .photo：
#   decide_image_batch_count → threading.image
#   decide_photo_batch_count → threading.photo
# 且 execute_on_condition 里「batch >= 对象数」时走 multi_thread_launcher，
# 即**每个对象一个线程、完全不设上限**。所以 image/photo 偏大会嵌套爆炸
# （16 章 × 30 图 = 480 线程同时 HTTP + Pillow decode），表现为下载卡死、
# 进度不动、速度掉 0。
# 另注：max_workers 是幽灵键（threading 为宽松 AdvancedDict，未知键静默忽略），
# batch_count 是旧版别名（会被改写成 image），两者都不是有效开关。
DOWNLOAD_IMAGE_CONCURRENCY = 16  # 单章内图片并发（基准实测 16×4 为最优组合）
DOWNLOAD_PHOTO_CONCURRENCY = 4   # 同时下载的章节数（16×4=64 峰值，PC 端安全）
DOWNLOAD_HTTP_TIMEOUT = 30       # 单请求超时秒（jmcomic 默认无超时，会被死连接挂死）

def _clamp_concurrency(value, ceiling: int) -> int:
    """把并发配置夹到安全区间 [1, ceiling]；缺失/非法值回落到 ceiling。

    这里刻意「封顶」而不是「保底」：并发一旦超过 ceiling，jmcomic 会在
    batch >= 对象数时退化成每对象一线程，嵌套后线程数失控反而更慢。
    """
    try:
        v = int(value)
    except (TypeError, ValueError):
        return ceiling
    if v < 1:
        return ceiling
    return min(v, ceiling)

def _detect_system_proxy() -> Optional[str]:
    """读取 Windows 系统代理（IE 设置）。返回 http://host:port 或 None。"""
    if sys.platform != "win32":
        return None
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
        enable, _t = winreg.QueryValueEx(key, "ProxyEnable")
        if not enable:
            return None
        server, _t = winreg.QueryValueEx(key, "ProxyServer")
        winreg.CloseKey(key)
        if not server:
            return None
        if "=" in server or ";" in server:
            # 形如 "http=127.0.0.1:7890;https=127.0.0.1:7890;ftp=..."
            chosen = ""
            for part in server.split(";"):
                if part.startswith(("https=", "http=")):
                    chosen = part.split("=", 1)[1]
                    break
            server = chosen
        if not server:
            return None
        if not server.startswith(("http://", "https://")):
            server = "http://" + server
        return server
    except Exception:
        return None

class OptionMixin:
    """option 构建、代理与客户端复用。"""
    def _build_default_option_content(self) -> Dict:
        return {
            "client": {
                "retry_times": 5,
                "domain": [],
                # 关键性能修复：curl_cffi 默认（非 session）= 每张图重新 TLS 握手，
                # session 模式复用连接池，基准实测 +54% 速度（0.50→0.77MB/s）
                "postman": {"type": "curl_cffi_session"},
                "headers": {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": (
                        "text/html,application/xhtml+xml,application/xml;q=0.9,"
                        "image/webp,*/*;q=0.8"
                    ),
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive",
                },
            },
            "download": {
                "cache": True,
                "image": {"decode": True, "suffix": ".jpg"},
                # 真实并发开关（image=单章内图片并发，photo=同时下载章节数）
                "threading": {
                    "image": DOWNLOAD_IMAGE_CONCURRENCY,
                    "photo": DOWNLOAD_PHOTO_CONCURRENCY,
                },
            },
            "dir_rule": {
                "rule": "{Aid}/{Pid}",
                "base_dir": os.path.join(self.base_dir, "TempCache", "downloads"),
            },
        }

    def _merge_option_content(self, current: Dict, defaults: Dict) -> Dict:
        merged = dict(current)
        for key, default_value in defaults.items():
            current_value = merged.get(key)
            if key not in merged:
                merged[key] = default_value
            elif isinstance(current_value, dict) and isinstance(default_value, dict):
                merged[key] = self._merge_option_content(current_value, default_value)
        return merged

    def _write_option_file(self, option_content: Dict):
        os.makedirs(os.path.dirname(self.option_file), exist_ok=True)
        with open(self.option_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                option_content,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

    def _ensure_option_file(self):
        """确保 jm_option.yml 存在且不覆盖用户设置。"""
        default_content = self._build_default_option_content()

        if not os.path.exists(self.option_file):
            self._write_option_file(default_content)
            return

        try:
            with open(self.option_file, "r", encoding="utf-8") as f:
                current_content = yaml.safe_load(f) or {}
            if not isinstance(current_content, dict):
                raise ValueError("jm_option.yml must contain a YAML mapping")
        except Exception as exc:
            backup_file = f"{self.option_file}.bak"
            try:
                shutil.copy2(self.option_file, backup_file)
                log.warning(f"jm_option.yml 无法解析，已备份到 {backup_file}")
            except Exception as backup_error:
                log.warning(f"备份 jm_option.yml 失败: {backup_error}")
            log.info(f"重建默认 jm_option.yml: {exc}")
            self._write_option_file(default_content)
            return

        merged_content = self._merge_option_content(current_content, default_content)

        # 强制修正：下载目录必须跟随当前 BASE_DIR（避免移动目录后失效）
        merged_content.setdefault("dir_rule", {})
        merged_content["dir_rule"]["base_dir"] = os.path.join(
            self.base_dir, "TempCache", "downloads"
        )

        # 并发治理：清掉无效键，并把真实开关统一为实测最优默认（16×4）
        # 注意：并发无用户配置入口，老 yml 里的 8/2 全是历史默认值——必须
        # 主动提升（而非只封顶），否则新默认白定；封顶防手改超限线程爆炸。
        threading_cfg = merged_content.setdefault("download", {}).setdefault("threading", {})
        # batch_count 是旧版别名（jmcomic 会改写成 image，留着会覆盖我们的设置）
        # max_workers 从未被 jmcomic 读取，纯误导，一并清掉
        threading_cfg.pop("batch_count", None)
        threading_cfg.pop("max_workers", None)
        threading_cfg["image"] = _clamp_concurrency(DOWNLOAD_IMAGE_CONCURRENCY, 24)
        threading_cfg["photo"] = _clamp_concurrency(DOWNLOAD_PHOTO_CONCURRENCY, 8)

        # 连接复用：老配置缺 postman.type 时 jmcomic 默认非 session（每图重握手，
        # 基准实测慢 54%）——强制写为 curl_cffi_session（幂等修正）
        postman_cfg = merged_content.setdefault("client", {}).setdefault("postman", {})
        if postman_cfg.get("type") != "curl_cffi_session":
            postman_cfg["type"] = "curl_cffi_session"

        if merged_content != current_content:
            self._write_option_file(merged_content)

    def _build_option(self):
        import jmcomic
        option = jmcomic.create_option_by_file(self.option_file)
        self._apply_proxy(option)
        return option

    def _apply_proxy(self, option) -> None:
        """接管代理与超时（必须在 jmcomic 注入默认值之后运行）。

        硬约束：jmcomic 在 option 无 proxies 时会注入 DEFAULT_PROXIES
        =127.0.0.1:5788，所有请求打向本机死端口。因此这里**必须显式接管**：
        代理开 → 用户代理；代理关 → 跟随系统代理（探测不到则显式直连）。
        timeout 无条件注入（postman 会把 meta_data 合并进每个请求 kwargs）。
        """
        try:
            meta = option.client["postman"]["meta_data"]
            meta["timeout"] = DOWNLOAD_HTTP_TIMEOUT
            enabled = get_system_config("proxy_enabled")
            url = (get_system_config("proxy_url") or "").strip()
            if enabled not in (None, "0", "false", "False", "") and url:
                if "://" not in url:
                    url = "http://" + url
                meta["proxies"] = {"http": url, "https": url}
            else:
                sys_proxy = _detect_system_proxy()
                if sys_proxy:
                    meta["proxies"] = {"http": sys_proxy, "https": sys_proxy}
                    log.info(f"[jmcomic] 下载跟随系统代理: {sys_proxy}")
                else:
                    # 显式直连：不能用 proxies=None（会被 postman.merge_kwargs
                    # 跳过、漏回 jmcomic 默认代理），必须用「值为 None 的键」
                    meta["proxies"] = {"http": None, "https": None}
        except Exception as e:
            log.warning(f"应用代理设置失败: {e}")

    def _build_client(self):
        return self._build_option().build_jm_client()

    def _client_signature(self):
        """客户端复用签名：option 文件 mtime + 代理配置。任一变化即重建。"""
        try:
            mtime = os.path.getmtime(self.option_file) if os.path.exists(self.option_file) else 0
        except Exception:
            mtime = 0
        try:
            proxy_enabled = get_system_config("proxy_enabled")
            proxy_url = (get_system_config("proxy_url") or "").strip()
        except Exception:
            proxy_enabled = None
            proxy_url = ""
        return (mtime, proxy_enabled, proxy_url)

    def _get_client(self):
        """复用 jmcomic 客户端以保留 keep-alive 连接；代理 / option 变化时自动重建。"""
        sig = self._client_signature()
        with self._client_lock:
            if self._client is not None and self._client_sig == sig:
                return self._client
            client = self._build_client()
            self._client = client
            self._client_sig = sig
            return client

    # ─── 工具 ──────────────────────────────────────────────
