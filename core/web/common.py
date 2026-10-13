# -*- coding: utf-8 -*-
"""路由层公共设施：单例装配、统一响应、配置读取。

原 core/app.py 把这些散在模块顶层；现在收在一处，各蓝图只 import 用。
"""

from typing import Any, Dict

from flask import jsonify

from core.models.database import get_system_config
from core.services import subscription as sub_service  # noqa: F401  (对外 re-export)
from core.services.comic_manager import ComicManager
from core.services.download_manager import DownloadManager
from core.services.jm_crawler import get_jm_crawler  # noqa: F401  (对外 re-export)
from core.services.sync_manager import SyncManager

# ── 进程级单例（与拆分前一致：import 阶段构造，crawler 仍惰性） ──
comic_manager = ComicManager()
download_manager = DownloadManager()
sync_manager = SyncManager()

# 对外 re-export 清单：sub_service / get_jm_crawler 供各蓝图从这里取，
# 显式声明 __all__ 才不会被视为「导入未使用」（也让静态 lint 保持干净）。
__all__ = [
    "ALLOWED_SETTINGS",
    "SUB_PAGE_AUTHOR_LIMIT",
    "cfg",
    "cfg_bool",
    "cfg_int",
    "comic_manager",
    "download_manager",
    "fail",
    "get_jm_crawler",
    "ok",
    "sub_service",
    "sync_manager",
]

# 订阅页：单作者最多拉取作品数（与巡检上限区分，页面展示可稍多）
SUB_PAGE_AUTHOR_LIMIT = 40

# 允许写入的配置键白名单（防止客户端污染 system_config）
ALLOWED_SETTINGS = {
    "max_concurrent_downloads",
    "image_quality",
    "theme",
    "theme_night_start",
    "theme_night_end",
    "proxy_enabled",
    "proxy_url",
    "search_result_limit",
    "default_sort",
    "search_apply_blocks",
    "hide_downloaded_in_search",
    "hide_finished_in_search",
    "reader_chapter_toast",
    "reader_pages_per_screen",
    "reader_progress_color",
    "shelf_sort",
    "library_columns",
    "search_columns",
    "library_finished",
    "reader_wheel_mode",
    "sync_enabled",
    "sync_server_url",
    "sync_token",
}


# ── 统一响应 ───────────────────────────────────────────────
# 约定：成功 {"success": true, "data": ...}；失败 {"success": false, "message": ...}
# 这样前端只需判 success，不必逐个端点记忆字段名。

def ok(data: Any = None, **extra):
    payload: Dict[str, Any] = {"success": True}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return jsonify(payload)


def fail(message: str, **extra):
    payload: Dict[str, Any] = {"success": False, "message": message}
    payload.update(extra)
    return jsonify(payload)


# ── 配置读取小工具 ─────────────────────────────────────────

def cfg(key: str, default: str = "") -> str:
    v = get_system_config(key)
    return default if v is None else str(v)


def cfg_int(key: str, default: int, lo: int | None = None, hi: int | None = None) -> int:
    try:
        v = int(cfg(key, str(default)) or default)
    except (TypeError, ValueError):
        v = default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def cfg_bool(key: str, default: bool = True) -> bool:
    v = cfg(key, "1" if default else "0").strip().lower()
    return v not in ("0", "false", "off", "no")
