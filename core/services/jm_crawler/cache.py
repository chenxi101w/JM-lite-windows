# -*- coding: utf-8 -*-
"""封面与详情缓存（自 jm_crawler.py 拆出）。"""

import json
import os
import re
import threading
from typing import Dict, Optional

from core.logging_setup import get_logger

log = get_logger("jm_crawler")

class CacheMixin:
    """封面 / 详情缓存与详情抓取。"""
    def _parse_count(self, value) -> int:
        if value is None:
            return 0
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        text = str(value).strip()
        if not text:
            return 0
        text = text.replace(",", "").replace(" ", "").lower()
        match = re.search(r"(\d+(?:\.\d+)?)(亿|万|k|m|b|w)?", text)
        if not match:
            return 0
        number = float(match.group(1))
        unit = match.group(2) or ""
        multiplier = {
            "w": 10_000,
            "k": 1_000,
            "m": 1_000_000,
            "b": 1_000_000_000,
            "万": 10_000,
            "亿": 100_000_000,
        }.get(unit, 1)
        return int(number * multiplier)

    # ─── 本地缓存 ──────────────────────────────────────────

    def _load_cover_cache(self) -> Dict[str, str]:
        try:
            if os.path.exists(self.cover_cache_file):
                with open(self.cover_cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                log.info(f"加载封面缓存，数量: {len(cache)}")
                return cache
        except Exception as e:
            log.warning(f"加载封面缓存失败: {e}")
        return {}

    def _save_cover_cache(self):
        try:
            with open(self.cover_cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cover_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.warning(f"保存封面缓存失败: {e}")

    def _save_cover_cache_async(self):
        """后台线程落盘，避免每新增一张封面就全量同步写盘。

        与 _save_detail_cache_async 同款：批量搜索时封面会连续命中新键，
        同步写盘会让每次请求都 O(n) 重写整个 JSON 并阻塞响应线程。
        """
        if self._cover_save_in_progress:
            return
        self._cover_save_in_progress = True

        def _worker():
            try:
                with self._cover_save_lock:
                    self._save_cover_cache()
            finally:
                self._cover_save_in_progress = False

        threading.Thread(target=_worker, daemon=True).start()

    def _load_detail_cache(self) -> Dict[str, Dict]:
        try:
            if os.path.exists(self.detail_cache_file):
                with open(self.detail_cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                if isinstance(cache, dict):
                    return cache
        except Exception as e:
            log.warning(f"加载详情缓存失败: {e}")
        return {}

    def _save_detail_cache(self):
        try:
            with open(self.detail_cache_file, "w", encoding="utf-8") as f:
                json.dump(self.detail_cache, f, ensure_ascii=False, separators=(",", ":"))
        except Exception as e:
            log.warning(f"保存详情缓存失败: {e}")

    def _save_detail_cache_async(self):
        """后台线程落盘，避免大缓存时阻塞搜索响应。"""
        if self._detail_save_in_progress:
            return
        self._detail_save_in_progress = True

        def _worker():
            try:
                with self._detail_save_lock:
                    self._save_detail_cache()
            finally:
                self._detail_save_in_progress = False

        threading.Thread(target=_worker, daemon=True).start()

    # ─── 详情 / 封面 ───────────────────────────────────────

    def get_comic_info(self, album_id: int) -> Optional[Dict]:
        """获取漫画详细信息（详情模态 / 纯数字 ID 搜索用）。"""
        try:
            client = self._get_client()
            album = client.get_album_detail(album_id)
            if not album:
                return None

            # 章节数：album 迭代零额外请求（详情响应本身包含章节列表）。
            # 注意：jmcomic 的 Album 没有现成「全站页数」字段（page_count 通常为 0，
            # 单章相册才可能有值），逐章统计图片数需要 N 次请求，详情页不做。
            chapter_count = 0
            try:
                chapter_count = len(list(album))
            except Exception:
                pass

            comic_info = {
                "id": album_id,
                "title": getattr(album, "title", "Unknown"),
                "author": getattr(album, "author", "Unknown"),
                "cover": "",
                "tags": list(getattr(album, "tags", []) or []),
                "description": getattr(album, "description", ""),
                "favorites": self._parse_count(getattr(album, "likes", 0)),
                "pages": int(getattr(album, "page_count", 0) or 0),
                "chapters": chapter_count,
                "scramble_id": getattr(album, "scramble_id", ""),
                "works": list(getattr(album, "works", []) or []),
                "actors": list(getattr(album, "actors", []) or []),
                "keywords": list(getattr(album, "keywords", []) or []),
            }

            cover_url = self.get_cover_url(album_id)
            if cover_url:
                comic_info["cover"] = cover_url

            return comic_info

        except Exception as e:
            log.warning(f"获取漫画信息失败 {album_id}: {e}")
            return None

    def get_cover_url(self, album_id: int) -> str:
        """获取封面 URL（本地构造 + 缓存）。"""
        cache_key = str(album_id)
        if cache_key in self.cover_cache:
            return self.cover_cache[cache_key]
        try:
            # 使用 jmcomic 维护的图片 CDN 域名列表生成封面地址，避免失效的固定域名
            from jmcomic.jm_toolkit import JmcomicText
            cover_url = JmcomicText.get_album_cover_url(album_id)
            self.cover_cache[cache_key] = cover_url
            # 上限裁剪：与 detail_cache 保持一致，防止长期使用后无限膨胀
            if len(self.cover_cache) > 3000:
                self.cover_cache = dict(list(self.cover_cache.items())[-3000:])
            self._save_cover_cache_async()
            return cover_url
        except Exception as e:
            log.warning(f"获取封面 URL 失败 {album_id}: {e}")
            return ""

    def fetch_cover_bytes(self, jm_id: int, url: str):
        """拉取封面字节（复用带代理/session 的 client；多域名轮换重试）。

        背景：封面 img 标签由 WebView 直连，部分禁漫 CDN 域可能被网络环境
        阻断（用户偶发「封面没返回」）——服务端拉取走配置好的代理/session，
        并轮换 jmcomic 图片域列表，成功率远高于直连。失败返回 None。
        """
        candidates = []
        # 域记忆优先：上次成功的域排最前（搜索页批量封面时后续都走热域）
        if self._cover_ok_prefix:
            candidates.append(f"{self._cover_ok_prefix}/media/albums/{jm_id}.jpg")
        if url:
            candidates.append(url)
        try:
            import jmcomic
            for dom in jmcomic.JmModuleConfig.DOMAIN_IMAGE_LIST:
                u = f"https://{dom}/media/albums/{jm_id}.jpg"
                if u not in candidates:
                    candidates.append(u)
        except Exception:
            pass
        try:
            client = self._get_client()
        except Exception as e:
            log.info(f"封面拉取无可用 client: {e}")
            return None
        for u in candidates:
            try:
                # 显式短超时：封面上限 6 个候选域，逐个 30s 会拖到 3 分钟
                resp = client.postman.get(u, timeout=6)
                if getattr(resp, "status_code", 0) == 200 and getattr(resp, "content", None):
                    self._cover_ok_prefix = u.rsplit("/media/", 1)[0]
                    return resp.content
            except Exception:
                continue
        return None
