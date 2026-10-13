# -*- coding: utf-8 -*-
"""下载任务：全局并发调度、进度登记、取消/续下、历史记录。"""

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from flask import Blueprint, jsonify, request

from core.config import BASE_DIR
from core.logging_setup import get_logger
from core.models.database import (
    add_download_history,
    clear_download_history,
    delete_download_history,
    get_download_history,
    set_comic_categories,
)
from core.services.jm_crawler import DownloadCancelled
from core.web.common import cfg_int, comic_manager, download_manager, fail, get_jm_crawler, ok

bp = Blueprint("downloads", __name__)
log = get_logger("download")


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
        """置 cancelled 并返回 (是否存在, 取消事件)。真正退出前的清理由下载线程收尾。"""
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
_executor = None
_executor_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    """全局线程池：限制同时进行的下载任务数（设置项 max_concurrent_downloads）。"""
    global _executor
    if _executor is None:
        with _executor_lock:
            if _executor is None:
                limit = cfg_int("max_concurrent_downloads", 3, lo=1, hi=16)
                _executor = ThreadPoolExecutor(max_workers=limit, thread_name_prefix="jm-dl")
    return _executor


# ── 文件数判定（续下 / 空壳识别） ───────────────────────────

def _count_files(root: str) -> int:
    if not root or not os.path.isdir(root):
        return 0
    n = 0
    for _root, _dirs, files in os.walk(root):
        n += len(files)
    return n


def _downloaded_real_file_count(jm_id: int) -> int:
    """DownloadedComics 中该本的真实文件数（0 = 不存在或空壳）。"""
    try:
        d = comic_manager._find_downloaded_dir(jm_id)
    except Exception:
        d = None
    return _count_files(d)


def _tempcache_file_count(jm_id: int) -> int:
    """TempCache 中该本的残留文件数（>0 = 有已下部分，可续下）。"""
    return _count_files(os.path.join(BASE_DIR, "TempCache", "downloads", str(jm_id)))


# ── 任务体 ─────────────────────────────────────────────────

def _cancel_cleanup(download_id: str, jm_id: int, title: str) -> None:
    """取消下载：只停任务并记录历史——**保留 TempCache 已下部分供续下**。"""
    try:
        add_download_history(jm_id, title or "", "cancelled", "已取消（已下部分保留，可续下）")
    except Exception as e:
        log.warning("取消历史落库失败 %s: %s", jm_id, e)
    _registry.update(download_id, 0, "cancelled", "已取消（可续下）")
    threading.Timer(3.0, _registry.remove, args=(download_id,)).start()


def _run_download_task(jm_id, comic_info, download_id, category_ids, cancel_event):
    """下载任务实体（被线程池调用）。成功 / 失败 / 取消都负责进度清理与历史落库。"""
    title = comic_info.get("title", "")
    try:
        ok_flag = download_manager.download_comic(
            jm_id, comic_info,
            lambda p, s, m, e=None: _registry.update(download_id, p, s, m, e),
            cancel_check=(lambda: cancel_event.is_set()) if cancel_event else None,
        )
        if not ok_flag:
            add_download_history(jm_id, title, "failed", "下载未完成")
            _registry.update(download_id, 0, "error", "下载未完成")
            threading.Timer(30.0, _registry.remove, args=(download_id,)).start()
            return
        if category_ids:
            set_comic_categories(jm_id, category_ids)
        add_download_history(jm_id, title, "completed")
        threading.Timer(2.0, _registry.remove, args=(download_id,)).start()
    except DownloadCancelled:
        _cancel_cleanup(download_id, jm_id, title)
    except Exception as e:
        log.exception("下载任务异常 %s", jm_id)
        _registry.update(download_id, 0, "error", str(e))
        add_download_history(jm_id, title, "failed", str(e))
        # 失败任务同样延时清理（保留 30s 供前端展示错误）
        threading.Timer(30.0, _registry.remove, args=(download_id,)).start()


def _parse_category_ids(req) -> list:
    """从请求中解析 category_ids（支持 JSON body 和 query string）。"""
    if req.is_json:
        raw = (req.get_json(silent=True) or {}).get("category_ids", [])
    else:
        arg = req.args.get("category_ids")
        raw = arg.split(",") if arg else []
    out = []
    for c in raw:
        try:
            out.append(int(c))
        except (ValueError, TypeError):
            pass
    return out


def _new_download_id(jm_id: int) -> str:
    return f"{jm_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"


# ── 端点 ───────────────────────────────────────────────────

@bp.post("/api/download/<int:jm_id>")
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
                return fail("该漫画已下载", downloaded=True)
            if dc_files > 0:
                try:
                    comic_manager.delete_completely(jm_id)  # 清残渣（TempCache 保留供续下）
                except Exception as e:
                    log.warning("清空壳失败 %s: %s", jm_id, e)
        if _registry.is_downloading(jm_id):
            return fail("该漫画正在下载中，请勿重复提交", downloading=True)

        comic_info = get_jm_crawler().get_comic_info(jm_id)
        if not comic_info:
            return fail("未找到对应的漫画")

        download_id = _new_download_id(jm_id)
        cancel_event = _registry.register(download_id, jm_id, comic_info.get("title", ""))
        _get_executor().submit(_run_download_task, jm_id, comic_info, download_id,
                               list(_parse_category_ids(request)), cancel_event)
        return ok(None, download_id=download_id, message="下载任务已启动")
    except Exception as e:
        return fail(f"下载失败: {e}")


@bp.post("/api/download/batch")
def api_download_batch():
    """批量下载。body: {"ids": [123, 456, ...], "category_ids": [1, 2]}"""
    try:
        raw_ids = (request.get_json(force=True, silent=True) or {}).get("ids", [])
        if not raw_ids:
            return fail("请提供漫画 ID 列表")

        jm_ids = []
        for rid in raw_ids:
            try:
                jm_ids.append(int(rid))
            except (ValueError, TypeError):
                continue
        if not jm_ids:
            return fail("没有有效的漫画 ID")

        category_ids = _parse_category_ids(request)
        executor = _get_executor()
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
            download_id = _new_download_id(jm_id)
            cancel_event = _registry.register(download_id, jm_id, comic_info.get("title", ""))
            executor.submit(_run_download_task, jm_id, comic_info, download_id,
                            list(category_ids), cancel_event)
            results.append({"jm_id": jm_id, "status": "downloading", "download_id": download_id})

        return ok(results)
    except Exception as e:
        return fail(f"批量下载失败: {e}")


@bp.get("/api/download/progress")
def api_download_progress_all():
    return ok(_registry.snapshot())


@bp.get("/api/download/progress/<download_id>")
def api_download_progress(download_id: str):
    rec = _registry.get(download_id)
    if rec is not None:
        return ok(rec)
    return fail("下载任务不存在")


@bp.delete("/api/download/progress/<download_id>")
def api_download_progress_delete(download_id: str):
    """从内存中的进行中列表移除一个任务（失败/卡住时清理用）。"""
    if _registry.get(download_id) is None:
        return fail("任务不存在")
    _registry.discard(download_id)
    return ok(None, message="已移除")


@bp.post("/api/download/cancel/<download_id>")
def api_download_cancel(download_id: str):
    """取消并删除：置取消事件 → 下载线程中断 → 由 _cancel_cleanup 收尾。

    UI 层立即置 cancelled（前端马上变已取消态并可重新下载同本），不再长时间
    停留「取消中」。TempCache 保留，已下部分可续下。
    """
    exists, evt = _registry.cancel(download_id)
    if not exists:
        return fail("任务不存在或已完成")
    if evt:
        evt.set()
    threading.Timer(3.0, _registry.remove, args=(download_id,)).start()
    return ok(None, message="已取消")


@bp.get("/api/download/history")
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
        return ok(history)
    except Exception as e:
        return fail(str(e))


@bp.delete("/api/download/history/<int:record_id>")
def api_download_history_delete(record_id: int):
    try:
        deleted = delete_download_history(record_id)
        return jsonify({"success": deleted, "message": "已删除" if deleted else "记录不存在"})
    except Exception as e:
        return fail(str(e))


@bp.delete("/api/download/history")
def api_download_history_clear():
    try:
        n = clear_download_history()
        return ok({"deleted": n}, message=f"已清空 {n} 条记录")
    except Exception as e:
        return fail(str(e))
