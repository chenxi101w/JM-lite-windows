# -*- coding: utf-8 -*-
"""系统类 API：健康检查 / 存储明细 / 设置读写 / 云同步。"""

import os
import sys
import time
from typing import Dict

from flask import Blueprint, jsonify, request

from core.config import APP_VERSION, BASE_DIR, DOWNLOAD_DIR, TEMP_CACHE_DIR
from core.logging_setup import get_logger
from core.models.database import get_all_configs, set_system_config
from core.web.common import ALLOWED_SETTINGS, fail, ok, sync_manager

bp = Blueprint("system", __name__)
log = get_logger("system")

# 存储明细全盘扫描有成本（数万文件），60s 缓存：关于页反复开关不重复扫
_STORAGE_SCAN_TTL = 60
_storage_scan_cache: Dict = {"ts": 0.0, "data": None}

# UserData 下各子目录的展示名（固定列出，空目录显示 0 B）
_STORAGE_LABELS = {
    "DownloadedComics": "已下载漫画",
    "TempCache": "临时缓存（封面/详情缓存 + 下载中转）",
    "core": "数据库与配置（comics.db / jm_option.yml）",
    "logs": "下载日志（download_log.jsonl）",
    "webview_data": "阅读器内核数据",
}


def _scan_storage() -> dict:
    """一次 os.walk 遍历安装根，按「UserData 各子目录 = 额外存储项、
    其余一切（exe/依赖/内置资源）= 程序本体」归桶。"""
    if getattr(sys, "frozen", False):
        install_root = os.path.dirname(sys.executable)
    else:  # 开发态近似：UserData 的上层
        install_root = os.path.dirname(BASE_DIR)
    user_top = os.path.relpath(BASE_DIR, install_root)

    buckets: Dict[str, int] = {}
    total = 0
    for dp, _dirs, files in os.walk(install_root):
        rel = os.path.relpath(dp, install_root)
        if rel == ".":
            key = "app"  # 安装根下的散文件（exe 等）
        else:
            parts = rel.split(os.sep)
            key = ("user:" + parts[1]) if (parts[0] == user_top and len(parts) > 1) \
                else ("user:(root)" if parts[0] == user_top else "app")
        for f in files:
            try:
                sz = os.path.getsize(os.path.join(dp, f))
            except OSError:
                continue
            buckets[key] = buckets.get(key, 0) + sz
            total += sz

    user_size = user_other = app_size = 0
    for key, size in buckets.items():
        if key.startswith("user:"):
            user_size += size
            if key[5:] not in _STORAGE_LABELS:
                user_other += size
        else:
            app_size += size

    # 五个固定额外存储项始终列出（空目录显示 0 B），用户要求逐项可见
    items = [{"label": label, "rel": f"{user_top}/{sub}", "size": buckets.get("user:" + sub, 0)}
             for sub, label in _STORAGE_LABELS.items()]
    if user_other:
        items.append({"label": "其他用户数据", "rel": f"{user_top}/其他", "size": user_other})
    items.append({"label": "程序本体（exe / 依赖 / 内置资源）",
                  "rel": f"安装根（除 {user_top}）", "size": app_size})
    items.sort(key=lambda x: -x["size"])
    return {"total_size": total, "user_size": user_size, "app_size": app_size, "items": items}


def _dir_size(root: str) -> int:
    total = 0
    try:
        for dp, _dirs, files in os.walk(root):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(dp, f))
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _storage_scan() -> dict:
    now = time.time()
    if _storage_scan_cache["data"] is None or now - _storage_scan_cache["ts"] > _STORAGE_SCAN_TTL:
        try:
            _storage_scan_cache["data"] = _scan_storage()
        except Exception as e:  # 扫描失败不能拖垮关于页
            log.warning("存储扫描失败: %s", e)
            _storage_scan_cache["data"] = {"total_size": 0, "user_size": 0,
                                           "app_size": 0, "items": []}
        _storage_scan_cache["ts"] = now
    return _storage_scan_cache["data"]


@bp.get("/api/ping")
def api_ping():
    # 注意：此处保持旧契约 {"ok": ...}（启动探活按 ok 判定），未并入统一响应
    return jsonify({"ok": True, "app": "JMComicLite", "version": APP_VERSION})


@bp.get("/api/about")
def api_about():
    scan = _storage_scan()
    return ok({
        "version": APP_VERSION,
        "base_dir": BASE_DIR,
        "download_dir": DOWNLOAD_DIR,
        "download_size": _dir_size(DOWNLOAD_DIR),
        "cache_size": _dir_size(TEMP_CACHE_DIR),
        "storage_items": scan["items"],
        "total_size": scan["total_size"],
        "user_size": scan["user_size"],
        "app_size": scan["app_size"],
    })


@bp.get("/api/settings")
def api_settings_get():
    return ok(get_all_configs())


@bp.post("/api/settings")
def api_settings_save():
    data = request.get_json(silent=True) or {}
    for k, v in data.items():
        if k in ALLOWED_SETTINGS and isinstance(v, (str, int, float)):
            set_system_config(str(k), str(v))
    return ok(get_all_configs())


@bp.get("/api/sync/status")
def api_sync_status():
    return ok(sync_manager.status())


@bp.post("/api/sync/now")
def api_sync_now():
    try:
        result = sync_manager.sync_now()
        return ok(None, **result, status=sync_manager.status())
    except Exception as e:
        return fail(str(e), status=sync_manager.status())
