# -*- coding: utf-8 -*-
"""Flask 应用 —— 页面路由与 API。

M1 骨架 + M2 搜索链路 + M3 下载链路 + M4 阅读器。
"""

import json
import os
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, List

from flask import Flask, jsonify, redirect, render_template, request, send_file

from core.config import APP_VERSION, BASE_DIR, STATIC_DIR, TEMPLATE_DIR, load_app_version
from core.models.database import (
    BIT_FAVORITE,
    BIT_FINISHED,
    BIT_LOCAL,
    _get_conn,
    add_download_history,
    clear_download_history,
    delete_download_history,
    get_all_configs,
    get_blocked_sets,
    get_download_history,
    get_read_book_ids,
    get_system_config,
    has_bit,
    init_database,
    normalize_author,
    set_comic_categories,
    set_system_config,
    toggle_status_bit,
)
from core.services.comic_manager import ComicManager
from core.services.download_manager import DownloadManager
from core.services.filter_service import (
    ensure_aliases_seeded,
    expand_author,
    expand_tags,
    postprocess_results,
)
from core.services.jm_crawler import JMCrawler, DownloadCancelled, get_jm_crawler
from core.services import subscription as sub_service
from core.services import recycle as recycle_service
from core.services.sync_manager import SyncManager

load_app_version()

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.json.ensure_ascii = False

init_database()
ensure_aliases_seeded()

# 订阅页：单作者最多拉取作品数（与巡检上限区分，页面展示可稍多）
SUB_PAGE_AUTHOR_LIMIT = 40

# JMCrawler 改为惰性单例：import 阶段不构造（避免同步加载 cover/detail 大缓存
# 拖慢启动），首次搜索/下载/详情时由 get_jm_crawler() 创建。
jm_crawler = None
comic_manager = ComicManager()
download_manager = DownloadManager()
sync_manager = SyncManager()

# 订阅自动巡检（启动后延迟 3 分钟首检，此后每小时一次；daemon 线程）
sub_service.schedule(get_jm_crawler)

# 允许写入的配置键（白名单，防止客户端污染 system_config）
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


@app.context_processor
def inject_globals():
    return {"app_version": APP_VERSION, "app_name": "JM 轻量版"}


# ─── 页面路由 ──────────────────────────────────────────────

@app.get("/")
def index():
    return redirect("/search")


@app.get("/search")
def page_search():
    return render_template("search.html", active="search")


@app.get("/library")
def page_library():
    return render_template("library.html", active="library")


@app.get("/downloads")
def page_downloads():
    return render_template("downloads.html", active="downloads")


@app.get("/reader/<int:jm_id>")
def page_reader(jm_id: int):
    return render_template("reader.html", active="reader", jm_id=jm_id)


@app.get("/settings")
def page_settings():
    return render_template("settings.html", active="settings")


@app.get("/subscriptions")
def page_subscriptions():
    return render_template("subscriptions.html", active="subscriptions")


# ─── 基础 API ──────────────────────────────────────────────

@app.get("/api/ping")
def api_ping():
    return jsonify({"ok": True, "app": "JMComicLite", "version": APP_VERSION})


_storage_scan_cache = {"ts": 0.0, "data": None}


def _scan_storage() -> dict:
    """一次 os.walk 遍历安装根，按「UserData 各子目录 = 额外存储项、
    其余一切（exe/依赖/内置资源）= 程序本体」归桶。"""
    if getattr(sys, "frozen", False):
        install_root = os.path.dirname(sys.executable)
    else:  # 开发态近似：UserData 的上层
        install_root = os.path.dirname(BASE_DIR)
    user_top = os.path.relpath(BASE_DIR, install_root)

    labels = {
        "DownloadedComics": "已下载漫画",
        "TempCache": "临时缓存（封面/详情缓存 + 下载中转）",
        "core": "数据库与配置（comics.db / jm_option.yml）",
        "logs": "下载日志（download_log.jsonl）",
        "webview_data": "阅读器内核数据",
    }
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

    items = []
    user_size = 0
    user_other = 0
    app_size = 0
    for key, size in buckets.items():
        if key.startswith("user:"):
            user_size += size
            sub = key[5:]
            if sub not in labels:
                user_other += size
        else:
            app_size += size
    # 五个固定额外存储项始终列出（空目录显示 0 B），用户要求逐项可见
    for sub, label in labels.items():
        items.append({"label": label, "rel": f"{user_top}/{sub}",
                      "size": buckets.get("user:" + sub, 0)})
    if user_other:
        items.append({"label": "其他用户数据", "rel": f"{user_top}/其他", "size": user_other})
    items.append({"label": "程序本体（exe / 依赖 / 内置资源）", "rel": f"安装根（除 {user_top}）", "size": app_size})
    items.sort(key=lambda x: -x["size"])
    return {"total_size": total, "user_size": user_size, "app_size": app_size, "items": items}


@app.get("/api/about")
def api_about():
    from core.config import BASE_DIR, DOWNLOAD_DIR, TEMP_CACHE_DIR

    def _dir_size(root):
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

    # 存储明细全盘扫描有成本（数万文件），60s 缓存：关于页反复开关不重复扫
    now = time.time()
    if _storage_scan_cache["data"] is None or now - _storage_scan_cache["ts"] > 60:
        try:
            _storage_scan_cache["data"] = _scan_storage()
        except Exception:
            _storage_scan_cache["data"] = {"total_size": 0, "user_size": 0, "app_size": 0, "items": []}
        _storage_scan_cache["ts"] = now
    scan = _storage_scan_cache["data"]

    return jsonify({"success": True, "data": {
        "version": APP_VERSION,
        "base_dir": BASE_DIR,
        "download_dir": DOWNLOAD_DIR,
        "download_size": _dir_size(DOWNLOAD_DIR),
        "cache_size": _dir_size(TEMP_CACHE_DIR),
        "storage_items": scan["items"],
        "total_size": scan["total_size"],
        "user_size": scan["user_size"],
        "app_size": scan["app_size"],
    }})


# ─── 云同步 API ────────────────────────────────────────────

@app.get("/api/sync/status")
def api_sync_status():
    return jsonify({"success": True, "data": sync_manager.status()})


@app.post("/api/sync/now")
def api_sync_now():
    try:
        result = sync_manager.sync_now()
        return jsonify({"success": True, **result, "status": sync_manager.status()})
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "status": sync_manager.status()})


@app.get("/api/settings")
def api_settings_get():
    return jsonify({"success": True, "data": get_all_configs()})


@app.post("/api/settings")
def api_settings_save():
    data = request.get_json(silent=True) or {}
    for k, v in data.items():
        if k in ALLOWED_SETTINGS and isinstance(v, (str, int, float)):
            set_system_config(str(k), str(v))
    return jsonify({"success": True, "data": get_all_configs()})


# ─── 搜索公共逻辑 ──────────────────────────────────────────

def _filter_blocked(results: List[Dict]) -> List[Dict]:
    """从搜索结果中剔除已被拉黑的作品 / 作者 / 标签（与后续书架一致）。

    所有搜索入口统一过滤，保证屏蔽在任何页面都生效。
    """
    if not results:
        return results
    blocked = get_blocked_sets()
    if not (blocked["works"] or blocked["authors"] or blocked["tags"]):
        return results
    out = []
    for c in results:
        cid = c.get("id")
        if cid is not None and cid in blocked["works"]:
            continue
        author = c.get("author")
        if author and normalize_author(author) in blocked["authors"]:
            continue
        tags = c.get("tags") or []
        if any(str(t) in blocked["tags"] for t in tags):
            continue
        out.append(c)
    return out


def _local_status_map(ids: List[int]) -> Dict[int, Dict]:
    """批量取本地状态（comic_status 位掩码）：{jm_id: {downloaded/favorite/finished}}。"""
    out: Dict[int, Dict] = {}
    if not ids:
        return out
    try:
        qs = ",".join("?" * len(ids))
        rows = _get_conn().execute(
            f"SELECT book_id, status FROM comic_status WHERE book_id IN ({qs})", ids
        ).fetchall()
        for r in rows:
            st = int(r["status"])
            out[int(r["book_id"])] = {
                "downloaded": 1 if has_bit(st, BIT_LOCAL) else 0,
                "favorite": 1 if has_bit(st, BIT_FAVORITE) else 0,
                "finished": 1 if has_bit(st, BIT_FINISHED) else 0,
            }
    except Exception:
        pass
    return out


def _enrich_and_filter_search(results: List[Dict]) -> List[Dict]:
    """搜索结果后处理：
    - 按 search_apply_blocks 决定是否应用黑名单过滤（默认应用）
    - 附加 downloaded / favorite / finished 状态（本地库）
    - 按 hide_downloaded_in_search / hide_finished_in_search 隐藏或标记灰显
    """
    if not results:
        return results or []

    apply_blocks = (get_system_config("search_apply_blocks") or "1").strip().lower() \
        not in ("0", "false", "off", "no")
    if apply_blocks:
        results = _filter_blocked(results)

    ids = []
    for c in results:
        try:
            ids.append(int(c.get("id") or 0))
        except Exception:
            pass
    local_map = _local_status_map(ids)

    mode_dl = (get_system_config("hide_downloaded_in_search") or "hide").strip().lower()
    mode_fin = (get_system_config("hide_finished_in_search") or "hide").strip().lower()

    out = []
    for c in results:
        try:
            jid = int(c.get("id") or 0)
        except Exception:
            jid = 0
        info = local_map.get(jid)
        c["downloaded"] = 1 if info and info.get("downloaded") else 0
        c["favorite"] = (info or {}).get("favorite") or 0
        c["finished"] = (info or {}).get("finished") or 0
        if mode_dl == "hide" and c["downloaded"]:
            continue
        if mode_fin == "hide" and c["finished"]:
            continue
        out.append(c)
    return out


def _default_order_by() -> str:
    v = (get_system_config("default_sort") or "mr").strip().lower()
    return v if v in ("mr", "mv", "mp") else "mr"


# ─── 搜索 API ──────────────────────────────────────────────

@app.get("/api/search/jm/<int:jm_id>")
def search_by_jm_id(jm_id: int):
    try:
        info = get_jm_crawler().get_comic_info(jm_id)
        if not info:
            return jsonify({"success": False, "message": "未找到对应的漫画"})
        blocked = get_blocked_sets()
        cid = info.get("id")
        if (cid is not None and cid in blocked["works"]) or (
            info.get("author") and normalize_author(info.get("author")) in blocked["authors"]
        ):
            return jsonify({"success": False, "message": "该作品已被屏蔽"})
        # 「看过」入账（云同步账本）：打开详情即算看过
        try:
            from core.models.database import touch_comic_status
            touch_comic_status(
                jm_id,
                title=info.get("title"), author=info.get("author"),
                cover_url=info.get("cover"),
                tags=",".join(info.get("tags") or []) if isinstance(info.get("tags"), list) else info.get("tags"),
            )
        except Exception:
            pass
        return jsonify({"success": True, "data": info})
    except Exception as e:
        return jsonify({"success": False, "message": f"搜索失败: {str(e)}"})


@app.get("/api/detail/<int:jm_id>")
def api_detail(jm_id: int):
    """详情模态数据（与搜索同源）。"""
    return search_by_jm_id(jm_id)


@app.get("/api/cover/<int:jm_id>")
def api_cover(jm_id: int):
    """封面 URL（本地构造，无网络请求）。"""
    try:
        url = get_jm_crawler().get_cover_url(jm_id)
        return jsonify({"success": bool(url), "data": {"id": jm_id, "cover": url}})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.get("/api/search/keyword")
def api_search_keyword():
    keyword = request.args.get("keyword", "").strip()
    sort_order = request.args.get("sort", "desc")
    order_by = request.args.get("order_by", "") or _default_order_by()
    time_range = request.args.get("time", "a")
    page = request.args.get("page", "1").strip()
    if not keyword:
        return jsonify({"success": False, "message": "关键词不能为空"})
    try:
        page_num = max(1, int(page))
        results = get_jm_crawler().search_by_keyword(
            keyword, sort_order, page=page_num, order_by=order_by, time_range=time_range,
        )
        results = postprocess_results(results)
        results = _enrich_and_filter_search(results)
        return jsonify({"success": True, "data": results, "order_by": order_by})
    except Exception as e:
        return jsonify({"success": False, "message": f"搜索失败: {str(e)}"})


@app.get("/api/search/tags")
def api_search_tags():
    tags = request.args.get("tags", "").strip()
    if not tags:
        return jsonify({"success": False, "message": "请选择至少一个标签"})
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    if not tag_list:
        return jsonify({"success": False, "message": "请选择至少一个标签"})
    try:
        try:
            limit = int(get_system_config("search_result_limit") or "80")
        except (ValueError, TypeError):
            limit = 80
        mode = request.args.get("mode", "or").strip().lower()
        if mode not in ("or", "and"):
            mode = "or"
        # 别名展开：每个标签一并检索其同义词；命中用户实际输入名的排前面
        expanded = expand_tags(tag_list)
        results, stats = get_jm_crawler().search_by_tags(
            expanded, mode=mode, max_total=limit, input_tags=tag_list,
        )
        results = postprocess_results(results)
        results = _enrich_and_filter_search(results)
        return jsonify({"success": True, "data": results, "stats": stats})
    except Exception as e:
        return jsonify({"success": False, "message": f"搜索失败: {str(e)}"})


@app.get("/api/search/author")
def api_search_author():
    author = request.args.get("author", "").strip()
    if not author:
        return jsonify({"success": False, "message": "作者不能为空"})
    try:
        try:
            limit = int(get_system_config("search_result_limit") or "80")
        except (ValueError, TypeError):
            limit = 80
        # 别名展开：作者名一并检索其同义署名
        results = []
        seen = set()
        for a in expand_author(author):
            for c in get_jm_crawler().search_by_author(a, max_total=limit):
                cid = c.get("id")
                if cid not in seen:
                    seen.add(cid)
                    results.append(c)
        results = postprocess_results(results)
        results = _enrich_and_filter_search(results)
        return jsonify({"success": True, "data": results, "author": author})
    except Exception as e:
        return jsonify({"success": False, "message": f"搜索失败: {str(e)}"})


@app.get("/api/search/enrich")
def api_search_enrich():
    """批量补充卡片详情（标签等），供前端对可见卡片按需调用。"""
    ids_param = request.args.get("ids", "").strip()
    if not ids_param:
        return jsonify({"success": False, "message": "缺少 ids 参数"})
    album_ids = []
    for raw in ids_param.split(","):
        raw = raw.strip()
        if raw and raw.isdigit():
            album_ids.append(int(raw))
    album_ids = album_ids[:12]
    if not album_ids:
        return jsonify({"success": False, "message": "没有可用的 ids"})
    try:
        details = get_jm_crawler().get_search_result_details(album_ids)
        return jsonify({"success": True, "data": details})
    except Exception as e:
        return jsonify({"success": False, "message": f"补充详情失败: {str(e)}"})


# ─── 下载任务调度（全局并发上限） ───────────────────────────
# 全局线程池：限制同时进行的下载任务数（对应设置项 max_concurrent_downloads）。
# 单本与批量下载都提交到这里，天然保证总并发不超过上限。

class _DownloadRegistry:
    """进行中下载的内存状态（单例 _registry），线程安全。

    状态机：starting → preparing → downloading → processing → completed
            （任意阶段可转 cancelled / error；终态短暂保留供前端展示后移出）
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._progress: dict = {}   # download_id -> 前端轮询用的进度记录
        self._events: dict = {}     # download_id -> 取消信号 Event

    def register(self, download_id: str, jm_id: int, title: str) -> threading.Event:
        """登记新任务并返回其取消事件。"""
        evt = threading.Event()
        with self._lock:
            self._events[download_id] = evt
            self._progress[download_id] = {
                "progress": 0, "status": "starting", "message": "开始下载...",
                "jm_id": jm_id, "title": title,
                "done": 0, "total": 0, "bytes": 0, "images": 0,
            }
        return evt

    def update(self, download_id: str, progress: int, status: str, message: str,
               extra: dict = None) -> None:
        """更新进度（extra 里 done/total/bytes/images 会被透传，供前端展示）。"""
        with self._lock:
            rec = self._progress.get(download_id)
            if rec is None:
                return
            rec["progress"] = progress
            rec["status"] = status
            rec["message"] = message
            if isinstance(extra, dict):
                for key in ("done", "total", "bytes", "images"):
                    if key in extra:
                        try:
                            rec[key] = int(extra[key])
                        except (TypeError, ValueError):
                            pass

    def is_downloading(self, jm_id: int) -> bool:
        """该漫画是否已有进行中的任务（防重复下载：同一本被点两次会起两个任务）。"""
        with self._lock:
            return any(
                r.get("jm_id") == jm_id and r.get("status") not in
                ("completed", "error", "cancelled")
                for r in self._progress.values()
            )

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._progress)

    def get(self, download_id: str):
        with self._lock:
            return self._progress.get(download_id)

    def cancel(self, download_id: str):
        """置 cancelled 并返回 (是否存在, 取消事件)。

        UI 层立即生效；真正退出前的清理由下载线程的 DownloadCancelled →
        _cancel_download_cleanup 收尾（对已移除记录是 no-op）。
        """
        with self._lock:
            rec = self._progress.get(download_id)
            if rec is None:
                return False, None
            if rec.get("status") != "cancelled":
                rec["status"] = "cancelled"
                rec["message"] = "已取消"
            return True, self._events.get(download_id)

    def discard(self, download_id: str) -> None:
        """前端手动移除记录（DELETE 端点）。"""
        with self._lock:
            self._progress.pop(download_id, None)

    def remove(self, download_id: str) -> None:
        """任务结束后移出列表（历史已落库），并清掉取消事件。"""
        with self._lock:
            self._progress.pop(download_id, None)
            self._events.pop(download_id, None)


_registry = _DownloadRegistry()
_dl_executor = None


def _get_dl_executor():
    global _dl_executor
    if _dl_executor is None:
        try:
            limit = int(get_system_config("max_concurrent_downloads") or "3")
        except (ValueError, TypeError):
            limit = 3
        limit = max(1, min(16, limit))
        _dl_executor = ThreadPoolExecutor(max_workers=limit, thread_name_prefix="jm-dl")
    return _dl_executor


def _downloaded_real_file_count(jm_id: int) -> int:
    """DownloadedComics 中该本的真实文件数（0 = 不存在或空壳）。"""
    try:
        d = comic_manager._find_downloaded_dir(jm_id)
    except Exception:
        d = None
    if not d or not os.path.isdir(d):
        return 0
    n = 0
    for _root, _dirs, files in os.walk(d):
        n += len(files)
    return n


def _tempcache_file_count(jm_id: int) -> int:
    """TempCache 中该本的残留文件数（>0 = 有已下部分，可续下）。"""
    d = os.path.join(BASE_DIR, "TempCache", "downloads", str(jm_id))
    if not os.path.isdir(d):
        return 0
    n = 0
    for _root, _dirs, files in os.walk(d):
        n += len(files)
    return n


def _cancel_download_cleanup(download_id: str, jm_id: int, title: str) -> None:
    """取消下载：只停任务并记录历史——**保留 TempCache 已下部分供续下**。

    续下语义：取消/中断后重新下载同一本时，已下好的图会被 jmcomic 的
    skip 机制自动跳过、从断点继续。想彻底清掉请在书架里删除该本。
    """
    try:
        add_download_history(jm_id, title or "", "cancelled", "已取消（已下部分保留，可续下）")
    except Exception:
        pass
    _registry.update(download_id, 0, "cancelled", "已取消（可续下）")
    # 短暂保留以展示「已取消」，随后移出「进行中」列表
    threading.Timer(3.0, _registry.remove, args=(download_id,)).start()


def _run_download_task(jm_id, comic_info, download_id, category_ids, cancel_event):
    """下载任务实体（被线程池调用）。成功 / 失败 / 取消都负责进度清理与历史落库。"""
    try:
        ok = download_manager.download_comic(
            jm_id, comic_info,
            lambda p, s, m, e=None: _registry.update(download_id, p, s, m, e),
            cancel_check=(lambda: cancel_event.is_set()) if cancel_event else None,
        )
        if not ok:
            add_download_history(jm_id, comic_info.get("title", ""), "failed", "下载未完成")
            _registry.update(download_id, 0, "error", "下载未完成")
            threading.Timer(30.0, _registry.remove, args=(download_id,)).start()
            return
        if category_ids:
            set_comic_categories(jm_id, category_ids)
        add_download_history(jm_id, comic_info.get("title", ""), "completed")
        # 短暂保留以便前端提示，随后移出「进行中」列表
        threading.Timer(2.0, _registry.remove, args=(download_id,)).start()
    except DownloadCancelled:
        _cancel_download_cleanup(download_id, jm_id, comic_info.get("title", ""))
    except Exception as e:
        _registry.update(download_id, 0, "error", str(e))
        add_download_history(jm_id, comic_info.get("title", ""), "failed", str(e))
        # 失败任务同样延时清理（保留 30s 供前端展示错误）
        threading.Timer(30.0, _registry.remove, args=(download_id,)).start()


def _parse_category_ids(req) -> list:
    """从请求中解析 category_ids（支持 JSON body 和 query string）。"""
    cids = []
    if req.is_json:
        data = req.get_json(silent=True) or {}
        raw = data.get("category_ids", [])
    else:
        raw = req.args.get("category_ids", "").split(",") if req.args.get("category_ids") else []
    for c in raw:
        try:
            cids.append(int(c))
        except (ValueError, TypeError):
            pass
    return cids


# ─── 下载 API ──────────────────────────────────────────────

@app.post("/api/download/<int:jm_id>")
def api_download_comic(jm_id: int):
    """下载单本漫画（可选分类）。"""
    try:
        if comic_manager.is_comic_downloaded(jm_id):
            # 未完成判定（续下前提）：在库文件数 < TempCache 残留数 → 是空壳/半壳
            # （假完成时代残渣，如只搬了 1 个封面文件），清壳放行续下；
            # 在库文件 >= 残留（正常已下载，TempCache=0）才拦「已下载」。
            dc_files = _downloaded_real_file_count(jm_id)
            tc_files = _tempcache_file_count(jm_id)
            if dc_files > tc_files and dc_files > 0:
                return jsonify({"success": False, "message": "该漫画已下载", "downloaded": True})
            if dc_files > 0:
                try:
                    comic_manager.delete_completely(jm_id)   # 清不完整残渣（TempCache 保留供续下）
                except Exception:
                    pass
        if _registry.is_downloading(jm_id):
            return jsonify({"success": False, "message": "该漫画正在下载中，请勿重复提交", "downloading": True})

        comic_info = get_jm_crawler().get_comic_info(jm_id)
        if not comic_info:
            return jsonify({"success": False, "message": "未找到对应的漫画"})

        category_ids = _parse_category_ids(request)
        download_id = f"{jm_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        cancel_event = _registry.register(download_id, jm_id, comic_info.get("title", ""))
        _get_dl_executor().submit(_run_download_task, jm_id, comic_info, download_id, list(category_ids), cancel_event)
        return jsonify({"success": True, "download_id": download_id, "message": "下载任务已启动"})
    except Exception as e:
        return jsonify({"success": False, "message": f"下载失败: {str(e)}"})


@app.post("/api/download/batch")
def api_download_batch():
    """批量下载。body: {"ids": [123, 456, ...], "category_ids": [1, 2]}"""
    try:
        data = request.get_json(force=True, silent=True) or {}
        raw_ids = data.get("ids", [])
        if not raw_ids:
            return jsonify({"success": False, "message": "请提供漫画 ID 列表"})

        jm_ids = []
        for rid in raw_ids:
            try:
                jm_ids.append(int(rid))
            except (ValueError, TypeError):
                continue
        if not jm_ids:
            return jsonify({"success": False, "message": "没有有效的漫画 ID"})

        category_ids = _parse_category_ids(request)
        ex = _get_dl_executor()

        results = []
        for jm_id in jm_ids:
            if comic_manager.is_comic_downloaded(jm_id):
                results.append({"jm_id": jm_id, "status": "skipped", "message": "已下载"})
                continue
            if _registry.is_downloading(jm_id):
                results.append({"jm_id": jm_id, "status": "skipped", "message": "已在下载中"})
                continue
            comic_info = get_jm_crawler().get_comic_info(jm_id)
            if not comic_info:
                results.append({"jm_id": jm_id, "status": "error", "message": "未找到漫画"})
                continue

            download_id = f"{jm_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            cancel_event = _registry.register(download_id, jm_id, comic_info.get("title", ""))
            ex.submit(_run_download_task, jm_id, comic_info, download_id, list(category_ids), cancel_event)
            results.append({"jm_id": jm_id, "status": "downloading", "download_id": download_id})

        return jsonify({"success": True, "data": results})
    except Exception as e:
        return jsonify({"success": False, "message": f"批量下载失败: {str(e)}"})


@app.get("/api/download/progress")
def api_download_progress_all():
    return jsonify({"success": True, "data": _registry.snapshot()})


@app.get("/api/download/progress/<download_id>")
def api_download_progress(download_id: str):
    rec = _registry.get(download_id)
    if rec is not None:
        return jsonify({"success": True, "data": rec})
    return jsonify({"success": False, "message": "下载任务不存在"})


@app.delete("/api/download/progress/<download_id>")
def api_download_progress_delete(download_id: str):
    """从内存中的进行中列表移除一个任务（失败/卡住时清理用）。"""
    if _registry.get(download_id) is not None:
        _registry.discard(download_id)
        return jsonify({"success": True, "message": "已移除"})
    return jsonify({"success": False, "message": "任务不存在"})


@app.post("/api/download/cancel/<download_id>")
def api_download_cancel(download_id: str):
    """取消并删除：置取消事件 → 下载线程中断 → 清理 TempCache + 本地内容 + 历史。

    UI 层立即置 cancelled（前端马上变已取消态并可重新下载同本），不再长时间
    停留「取消中」——真正退出前的清理由下载线程的
    DownloadCancelled → _cancel_download_cleanup 负责（对已移除记录是 no-op）。
    """
    exists, evt = _registry.cancel(download_id)
    if not exists:
        return jsonify({"success": False, "message": "任务不存在或已完成"})
    if evt:
        evt.set()
    # 短暂保留展示，随后移出「进行中」；TempCache/本地内容的清理由下载线程收尾
    threading.Timer(3.0, _registry.remove, args=(download_id,)).start()
    return jsonify({"success": True, "message": "已取消"})


@app.get("/api/download/history")
def api_download_history():
    try:
        history = get_download_history(50)
        for item in history:
            jm_id = item.get("jm_id")
            item["files_exist"] = comic_manager.is_comic_downloaded(jm_id) if jm_id else False
            # 可续下：未在库 + TempCache 有已下部分（续下按钮显示条件）
            item["resumable"] = bool(
                jm_id and not item["files_exist"] and _tempcache_file_count(jm_id) > 0
            )
        return jsonify({"success": True, "data": history})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.delete("/api/download/history/<int:record_id>")
def api_download_history_delete(record_id: int):
    try:
        ok = delete_download_history(record_id)
        return jsonify({"success": ok, "message": "已删除" if ok else "记录不存在"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.delete("/api/download/history")
def api_download_history_clear():
    try:
        n = clear_download_history()
        return jsonify({"success": True, "data": {"deleted": n}, "message": f"已清空 {n} 条记录"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


# ─── 阅读 API ──────────────────────────────────────────────

@app.get("/api/read/<int:jm_id>")
def api_read_comic(jm_id: int):
    try:
        if not comic_manager.is_comic_downloaded(jm_id):
            return jsonify({"success": False, "message": "该漫画尚未下载"})
        chapters = comic_manager.get_comic_chapters(jm_id)
        if not chapters:
            return jsonify({"success": False, "message": "没有可用的章节"})
        meta = comic_manager.get_comic_meta(jm_id) or {}
        # 「看过」入账（云同步账本）：打开阅读器即算看过；已入回收站的自动续期
        try:
            from core.models.database import touch_comic_status
            touch_comic_status(jm_id, title=meta.get("title"), author=meta.get("author"))
            recycle_service.renew(jm_id)
        except Exception:
            pass
        return jsonify({
            "success": True,
            "data": {
                "title": meta.get("title") or f"JM-{jm_id}",
                "chapters": chapters,
                "current_chapter": chapters[0]["id"],
                "current_chapter_pages": chapters[0]["pages"],
                "total_chapters": len(chapters),
                "read_progress": comic_manager.get_read_progress(jm_id),
            },
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"获取阅读数据失败: {str(e)}"})


@app.get("/api/read/<int:jm_id>/chapter/<chapter_id>")
def api_read_chapter(jm_id: int, chapter_id: str):
    try:
        if not comic_manager.is_comic_downloaded(jm_id):
            return jsonify({"success": False, "message": "该漫画尚未下载"})
        if not comic_manager.is_local_chapter(jm_id, chapter_id):
            return jsonify({"success": False, "message": "章节不存在"})
        chapters = comic_manager.get_comic_chapters(jm_id)
        target = next((ch for ch in chapters if ch["id"] == chapter_id), None)
        if not target:
            return jsonify({"success": False, "message": "章节不存在"})
        meta = comic_manager.get_comic_meta(jm_id) or {}
        return jsonify({
            "success": True,
            "data": {
                "title": meta.get("title") or f"JM-{jm_id}",
                "chapters": chapters,
                "current_chapter": target["id"],
                "current_chapter_pages": target["pages"],
                "total_chapters": len(chapters),
            },
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"获取章节数据失败: {str(e)}"})


@app.get("/api/comic/<int:jm_id>/page/<int:page_num>")
def api_comic_page(jm_id: int, page_num: int):
    try:
        chapter_id = request.args.get("chapter", None)
        # 轻量本地校验章节 id（不联网）：路径越界由 get_comic_page_path 的 realpath 兜底。
        if not comic_manager.is_local_chapter(jm_id, chapter_id):
            return jsonify({"success": False, "message": "章节不存在"}), 400
        page_path = comic_manager.get_comic_page_path(jm_id, page_num, chapter_id)
        if page_path and os.path.exists(page_path):
            return send_file(page_path)
        return jsonify({"success": False, "message": "页面不存在"}), 404
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.post("/api/read/<int:jm_id>/progress")
def api_save_read_progress(jm_id: int):
    """保存阅读进度（0 基页码）。翻页时前端防抖上报。"""
    data = request.get_json(silent=True) or {}
    try:
        page = int(data.get("page") or 0)
    except (ValueError, TypeError):
        page = 0
    comic_manager.update_read_progress(jm_id, max(0, page))
    return jsonify({"success": True})


@app.post("/api/status/<int:jm_id>/finished")
def api_status_finished(jm_id: int):
    """标记 / 取消「已读完」（阅读器翻到末章末尾自动调用）。

    读完 → 同时打回收标记（宽限 7 天后自动清本地，可重下）；取消读完 → 清标记。
    """
    data = request.get_json(silent=True) or {}
    on = bool(data.get("finished", True))
    toggle_status_bit(jm_id, BIT_FINISHED, on)
    try:
        if on:
            recycle_service.mark_finished(jm_id)
        else:
            recycle_service.restore(jm_id)
    except Exception:
        pass
    return jsonify({"success": True})


# ─── 书架 / 分类 API ───────────────────────────────────────

@app.get("/api/downloaded")
def api_downloaded():
    """已下载漫画列表。?category_id=N / ?uncategorized=1 筛选；排序取设置 shelf_sort。"""
    try:
        from core.models.database import get_category_comic_count  # noqa: F401
        category_id = request.args.get("category_id", type=int)
        uncategorized = request.args.get("uncategorized") == "1"
        sort = get_system_config("shelf_sort") or "download_desc"
        comics = comic_manager.get_downloaded_comics(
            category_id=category_id, uncategorized=uncategorized, sort=sort
        )
        # 标注是否被拉黑（作者/作品），供前端书架灰显
        blocked = get_blocked_sets()
        for c in comics:
            c["blocked"] = bool(
                (c.get("id") in blocked["works"])
                or (c.get("author") and normalize_author(c.get("author")) in blocked["authors"])
            )
        return jsonify({"success": True, "data": comics})
    except Exception as e:
        return jsonify({"success": False, "message": f"获取列表失败: {str(e)}"})


def _cover_mimetype(path: str) -> str:
    """按文件头检测封面真实 MIME（禁漫 CDN 会按 UA 协商返回 webp）。"""
    try:
        with open(path, "rb") as f:
            head = f.read(12)
        if head[:2] == b"\xff\xd8":
            return "image/jpeg"
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            return "image/webp"
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
    except Exception:
        pass
    return "image/jpeg"


# 封面失败负缓存：拉不到的本在 TTL 内直接返回占位图（避免每次页面加载
# 都做 6~8 个域 × 6s 的全轮询——单张失败要 7s+，整页封面会被拖垮）
_cover_fail_until: dict = {}
_COVER_FAIL_TTL = 600
_NO_COVER_PATH = os.path.join(STATIC_DIR, "img", "no_cover.svg")


def _send_no_cover():
    """封面兜底占位图（200，前端 img 永不破图）。"""
    return send_file(_NO_COVER_PATH, mimetype="image/svg+xml")


def _serve_cover(jm_id: int):
    """封面统一出口：缓存 → 负缓存 → 实时拉取 → 占位图兜底。

    拉取成功时：落 TempCache 缓存 + **顺手补书目录 cover.jpg**（历史缺封面
    的已下载本自愈）。任何失败路径都返回占位图，绝不让前端出现破图。
    """
    from core.config import TEMP_CACHE_DIR
    cache_path = os.path.join(TEMP_CACHE_DIR, f"cover_{jm_id}.jpg")
    try:
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
            return send_file(cache_path, mimetype=_cover_mimetype(cache_path))
    except Exception:
        pass
    if _cover_fail_until.get(jm_id, 0) > time.time():
        return _send_no_cover()
    try:
        crawler = get_jm_crawler()
        url = crawler.get_cover_url(jm_id)
        data = crawler.fetch_cover_bytes(jm_id, url)
        if data:
            tmp = cache_path + ".tmp"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, cache_path)
            _cover_fail_until.pop(jm_id, None)
            # 书目录自愈：该本已在库但缺 cover.jpg 时补齐
            try:
                d = comic_manager._find_downloaded_dir(jm_id)
                if d and not os.path.exists(os.path.join(d, "cover.jpg")):
                    with open(os.path.join(d, "cover.jpg"), "wb") as f:
                        f.write(data)
            except Exception:
                pass
            return send_file(cache_path, mimetype=_cover_mimetype(cache_path))
    except Exception as e:
        print(f"封面拉取失败 {jm_id}: {e}")
    _cover_fail_until[jm_id] = time.time() + _COVER_FAIL_TTL
    return _send_no_cover()


@app.get("/api/cover/proxy/<int:jm_id>")
def api_cover_proxy(jm_id: int):
    """远程封面的本地代理（服务端拉取 + 磁盘缓存 + 占位兜底）。

    img 直连部分禁漫 CDN 域可能被网络环境阻断（用户偶发「封面没返回」）——
    服务端走配置好的代理/session + 域名轮换拉取；一枚拉过即落盘
    cover_{id}.jpg。全失败时返回「暂无封面」占位图（200）并做 10 分钟
    负缓存——前端永不破图，也不会每次刷新都重新全轮询。
    """
    return _serve_cover(jm_id)


@app.get("/api/cover/downloaded/<int:jm_id>")
def api_cover_downloaded(jm_id: int):
    """本地已下载漫画的封面图：书目录 cover.jpg → 缓存 → 实时拉取(自愈) → 占位。"""
    try:
        comic_dir = comic_manager._find_downloaded_dir(jm_id)
        if comic_dir:
            cover = os.path.join(comic_dir, "cover.jpg")
            if os.path.exists(cover):
                return send_file(cover)
    except Exception:
        pass
    return _serve_cover(jm_id)


@app.delete("/api/delete/<int:jm_id>")
def api_delete_comic(jm_id: int):
    """删除本地 = 移入回收站（保留账本与封面，宽限 7 天，可重新下载恢复）。"""
    try:
        ok = recycle_service.trash_local(jm_id, comic_manager)
        return jsonify({"success": ok, "message": "已移入回收站" if ok else "删除失败"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


# ─── 回收站 API ────────────────────────────────────────────

@app.get("/api/recycle")
def api_recycle_list():
    try:
        # 打开回收站时顺手做一次到期检查（宽限已过的标记项清本地内容）
        recycle_service.purge_expired(comic_manager)
        items = recycle_service.list_for_ui(comic_manager)
        return jsonify({"success": True, "data": items, "grace_days": recycle_service.RECYCLE_GRACE_DAYS})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.post("/api/recycle/<int:jm_id>/restore")
def api_recycle_restore(jm_id: int):
    try:
        ok = recycle_service.restore(jm_id)
        return jsonify({"success": ok})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.delete("/api/recycle/<int:jm_id>")
def api_recycle_purge(jm_id: int):
    """彻底删除（不可恢复）。"""
    try:
        ok = recycle_service.purge_one(jm_id, comic_manager)
        return jsonify({"success": ok})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.post("/api/status/<int:jm_id>/favorite")
def api_status_favorite(jm_id: int):
    """收藏 / 取消收藏。"""
    data = request.get_json(silent=True) or {}
    on = bool(data.get("favorite", True))
    toggle_status_bit(jm_id, BIT_FAVORITE, on)
    return jsonify({"success": True})


# ─── 收藏备份（导出 / 导入，格式兼容手机端「JM 轻量版」）──────

def _favorites_payload() -> Dict:
    """构造收藏备份 JSON（零网络：detail_cache → 已下载表补元数据）。"""
    from core.models.database import get_favorite_ids
    ids = get_favorite_ids()
    crawler = get_jm_crawler()
    dcache = getattr(crawler, "detail_cache", {}) or {}
    # 已下载表的元数据兜底（一次查询）
    meta = {}
    if ids:
        try:
            from core.models.database import _get_conn as _db_conn
            marks = ",".join("?" for _ in ids)
            for r in _db_conn().execute(
                    f"SELECT jm_id, title, author FROM downloaded_comics WHERE jm_id IN ({marks})",
                    ids).fetchall():
                meta[int(r["jm_id"])] = {"title": r["title"], "author": r["author"]}
        except Exception:
            pass
    books = []
    for jm_id in ids:
        info = dcache.get(str(jm_id)) or {}
        m = meta.get(jm_id) or {}
        books.append({
            "id": jm_id,
            "title": info.get("title") or m.get("title") or "",
            "author": info.get("author") or m.get("author") or "",
            "coverUrl": info.get("cover") or "",
        })
    return {
        "app": "jmcomicreader",
        "type": "favorites",
        "version": 1,
        "exportedAt": int(time.time() * 1000),
        "favoriteBooks": books,
        "favTags": [],                       # 轻量版无标签库（保留字段供跨端兼容）
        "source": "jmcomicreader-lite",      # 桌面标识（手机端忽略）
    }


@app.post("/api/favorites/export")
def api_favorites_export():
    """导出收藏到 UserData/exports/（JSON，兼容手机端收藏备份，可跨端导入）。"""
    try:
        payload = _favorites_payload()
        export_dir = os.path.join(BASE_DIR, "UserData", "exports")
        os.makedirs(export_dir, exist_ok=True)
        filename = "jm_lite_favorites_%s.json" % datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(export_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return jsonify({"success": True, "data": {
            "path": path, "count": len(payload["favoriteBooks"]),
        }})
    except Exception as e:
        return jsonify({"success": False, "message": f"导出失败: {e}"})


@app.get("/api/favorites/export")
def api_favorites_export_raw():
    """导出收藏 JSON（浏览器直接下载用；桌面 UI 走 POST 写文件）。"""
    payload = _favorites_payload()
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    filename = "jm_lite_favorites_%s.json" % datetime.now().strftime("%Y%m%d")
    return app.response_class(
        body, mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=%s" % filename},
    )


@app.post("/api/favorites/import")
def api_favorites_import():
    """导入收藏备份（兼容手机端导出；已收藏的幂等跳过）。"""
    try:
        from core.models.database import get_comic_status
        data = request.get_json(silent=True) or {}
        books = data.get("favoriteBooks")
        if not isinstance(books, list):
            return jsonify({"success": False, "message": "不是有效的收藏备份（缺少 favoriteBooks）"})
        added = 0
        for item in books:
            try:
                jm_id = int((item or {}).get("id") or 0)
            except (TypeError, ValueError):
                continue
            if jm_id <= 0:
                continue
            if has_bit(get_comic_status(jm_id), BIT_FAVORITE):
                continue
            toggle_status_bit(jm_id, BIT_FAVORITE, True)
            added += 1
        return jsonify({"success": True, "data": {"total": len(books), "added": added}})
    except Exception as e:
        return jsonify({"success": False, "message": f"导入失败: {e}"})


@app.get("/api/categories")
def api_categories():
    """分类列表。?tree=1 返回树形结构。"""
    from core.models.database import get_all_categories, get_category_tree
    tree = request.args.get("tree", "0") == "1"
    data = get_category_tree() if tree else get_all_categories()
    return jsonify({"success": True, "data": data})


@app.post("/api/categories")
def api_category_create():
    from core.models.database import create_category
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"success": False, "message": "分类名称不能为空"})
    parent_id = data.get("parent_id")
    try:
        cid = create_category(name, parent_id)
        return jsonify({"success": True, "data": {"id": cid, "name": name}})
    except Exception as e:
        return jsonify({"success": False, "message": f"创建失败: {str(e)}"})


@app.put("/api/categories/<int:cat_id>")
def api_category_update(cat_id: int):
    from core.models.database import update_category
    data = request.get_json(silent=True) or {}
    if update_category(cat_id, name=data.get("name"), parent_id=data.get("parent_id")):
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "更新失败"})


@app.delete("/api/categories/<int:cat_id>")
@app.get("/api/categories/<int:cat_id>")
def api_category_remove(cat_id: int):
    """删除分类；GET ?count_only=1 用于删除前预检。

    分类非空时必须指定漫画去向（body {"reassign_to": <id|null>}），否则拒绝删除。
    """
    from core.models.database import (
        delete_category,
        delete_category_with_reassign,
        get_category_comic_count,
    )
    if request.args.get("count_only") == "1":
        return jsonify({"success": True, "count": get_category_comic_count(cat_id)})
    if request.method == "GET":
        return jsonify({"success": False, "message": "仅支持 DELETE 或 ?count_only=1"})

    data = request.get_json(silent=True) or {}
    raw = data.get("reassign_to", "__absent__")
    target = None
    if raw not in ("__absent__", None, "", "null"):
        try:
            target = int(raw)
        except (ValueError, TypeError):
            return jsonify({"success": False, "message": "reassign_to 无效"})

    cnt = get_category_comic_count(cat_id)
    if cnt > 0:
        if "reassign_to" not in data:
            return jsonify({
                "success": False, "need_reassign": True, "count": cnt,
                "message": f"该分类下有 {cnt} 部漫画，请先选择将它们移动到哪个分类",
            })
        ok = delete_category_with_reassign(cat_id, target)
    else:
        ok = delete_category(cat_id)
    if ok:
        return jsonify({"success": True, "count": cnt})
    return jsonify({"success": False, "message": "删除失败（分类不存在或目标分类无效）"})


@app.post("/api/categories/<int:cat_id>/move")
def api_category_move(cat_id: int):
    """移动分类（重定父级）。阻止移到自身或其子孙下，避免成环。"""
    from core.models.database import (
        get_category_descendant_ids,
        set_category_parent,
    )
    data = request.get_json(silent=True) or {}
    raw_parent = data.get("parent_id")
    parent_id = None
    if raw_parent is not None and str(raw_parent) != "" and str(raw_parent).lower() != "null":
        try:
            parent_id = int(raw_parent)
        except (ValueError, TypeError):
            return jsonify({"success": False, "message": "parent_id 无效"})
    if parent_id is not None:
        if parent_id == cat_id:
            return jsonify({"success": False, "message": "不能移动到自身"})
        if parent_id in get_category_descendant_ids(cat_id):
            return jsonify({"success": False, "message": "不能移动到其子分类下"})
    if set_category_parent(cat_id, parent_id):
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "移动失败"})


@app.get("/api/comic/<int:jm_id>/categories")
def api_comic_categories_get(jm_id: int):
    from core.models.database import get_comic_categories
    return jsonify({"success": True, "data": get_comic_categories(jm_id)})


@app.put("/api/comic/<int:jm_id>/categories")
def api_comic_categories_set(jm_id: int):
    data = request.get_json(silent=True) or {}
    cids = [int(c) for c in data.get("category_ids", []) if str(c).isdigit()]
    set_comic_categories(jm_id, cids)
    return jsonify({"success": True})


# ─── 订阅 API ──────────────────────────────────────────────

@app.get("/api/subscriptions")
def api_subscriptions():
    from core.models.database import get_subscriptions
    try:
        return jsonify({"success": True, "data": get_subscriptions()})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.post("/api/subscriptions")
def api_subscription_add():
    from core.models.database import find_subscription_by_author, upsert_subscription
    try:
        data = request.get_json(silent=True) or {}
        author = (data.get("author") or "").strip()
        if not author:
            return jsonify({"success": False, "message": "author 不能为空"})
        existing = find_subscription_by_author(author)
        if existing:
            return jsonify({"success": True, "id": existing["id"], "exists": True})
        sid = upsert_subscription(author)
        return jsonify({"success": True, "id": sid})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.delete("/api/subscriptions/<int:sid>")
def api_subscription_delete(sid: int):
    from core.models.database import delete_subscription
    try:
        delete_subscription(sid)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.post("/api/subscriptions/<int:sid>/clear-new")
def api_subscription_clear_new(sid: int):
    from core.models.database import clear_subscription_new_count
    try:
        clear_subscription_new_count(sid)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.post("/api/subscriptions/poll")
def api_subscription_poll():
    """手动触发一次订阅巡检。"""
    try:
        summary = sub_service.poll_all(get_jm_crawler)
        return jsonify({"success": True, **summary})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.get("/api/sub_updates")
def api_sub_updates():
    from core.models.database import get_sub_updates
    try:
        unseen = request.args.get("unseen") == "1"
        return jsonify({"success": True, "data": get_sub_updates(unseen_only=unseen)})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.post("/api/sub_updates/seen")
def api_sub_updates_seen():
    from core.models.database import mark_all_sub_updates_seen, mark_sub_update_seen
    try:
        data = request.get_json(silent=True) or {}
        if data.get("all"):
            mark_all_sub_updates_seen()
        else:
            book_id = data.get("book_id")
            if not book_id:
                return jsonify({"success": False, "message": "book_id 或 all 必填"})
            mark_sub_update_seen(int(book_id))
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.delete("/api/sub_updates")
def api_sub_updates_clear():
    from core.models.database import clear_all_sub_updates
    try:
        n = clear_all_sub_updates()
        return jsonify({"success": True, "deleted": n})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.get("/api/subscription-works")
def api_subscription_works():
    """订阅页：单个作者的全部作品。

    排序规则（用户需求）：未看的新作品在前、已看的老作品在后；两组内再分别按时间
    （JM 号越大越新）倒序。read 由本地 comic_status / downloaded_comics 判定。
    单作者搜索失败不抛 500，返回 error 字段由前端在对应区块提示，互不影响。
    """
    from core.services.jm_crawler import get_jm_crawler
    author = (request.args.get("author") or "").strip()
    if not author:
        return jsonify({"success": False, "message": "author 必填"})
    try:
        crawler = get_jm_crawler()
        works = crawler.search_by_author(author, max_total=SUB_PAGE_AUTHOR_LIMIT) or []
        ids = [int(c.get("id") or 0) for c in works if c.get("id")]
        read_set = get_read_book_ids(ids) if ids else set()
        out = []
        for c in works:
            cid = int(c.get("id") or 0)
            out.append({
                "id": cid,
                "title": c.get("title") or "",
                "author": c.get("author") or "",
                "cover": c.get("cover") or "",
                "read": cid in read_set,
            })
        # 未看(0)在前、已看(1)在后；组内按 id 倒序（新→旧）
        out.sort(key=lambda x: (0 if not x["read"] else 1, -x["id"]))
        return jsonify({"success": True, "author": author, "works": out})
    except Exception as e:
        return jsonify({"success": True, "author": author, "works": [], "error": str(e)})


# ─── 黑名单 API ────────────────────────────────────────────

@app.get("/api/blocklist")
def api_blocklist():
    from core.models.database import list_blocklist
    try:
        return jsonify({"success": True, "data": list_blocklist()})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.post("/api/blocklist")
def api_blocklist_add():
    from core.models.database import add_block
    try:
        data = request.get_json(silent=True) or {}
        btype = (data.get("type") or "").strip()
        value = (data.get("value") or "").strip()
        if btype not in ("author", "work", "tag"):
            return jsonify({"success": False, "message": "type 必须是 author/work/tag"})
        if not value:
            return jsonify({"success": False, "message": "value 不能为空"})
        bid = add_block(btype, value)
        return jsonify({"success": True, "id": bid})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.delete("/api/blocklist/<int:block_id>")
def api_blocklist_delete(block_id: int):
    from core.models.database import remove_block
    try:
        ok = remove_block(block_id)
        return jsonify({"success": ok})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})