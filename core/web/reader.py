# -*- coding: utf-8 -*-
"""阅读器 API：章节数据、页面图片、进度保存、读完标记。"""

import os

from flask import Blueprint, jsonify, request, send_file

from core.logging_setup import get_logger
from core.models.database import BIT_FINISHED, toggle_status_bit
from core.services import recycle as recycle_service
from core.web.common import comic_manager, fail, ok

bp = Blueprint("reader", __name__)
log = get_logger("reader")


@bp.get("/api/read/<int:jm_id>")
def api_read_comic(jm_id: int):
    try:
        if not comic_manager.is_comic_downloaded(jm_id):
            return fail("该漫画尚未下载")
        chapters = comic_manager.get_comic_chapters(jm_id)
        if not chapters:
            return fail("没有可用的章节")
        meta = comic_manager.get_comic_meta(jm_id) or {}
        # 「看过」入账（云同步账本）：打开阅读器即算看过；已入回收站的自动续期
        try:
            from core.models.database import touch_comic_status
            touch_comic_status(jm_id, title=meta.get("title"), author=meta.get("author"))
            recycle_service.renew(jm_id)
        except Exception as e:
            log.debug("看过入账/续期失败 %s: %s", jm_id, e)
        return ok({
            "title": meta.get("title") or f"JM-{jm_id}",
            "chapters": chapters,
            "current_chapter": chapters[0]["id"],
            "current_chapter_pages": chapters[0]["pages"],
            "total_chapters": len(chapters),
            "read_progress": comic_manager.get_read_progress(jm_id),
        })
    except Exception as e:
        return fail(f"获取阅读数据失败: {e}")


@bp.get("/api/read/<int:jm_id>/chapter/<chapter_id>")
def api_read_chapter(jm_id: int, chapter_id: str):
    try:
        if not comic_manager.is_comic_downloaded(jm_id):
            return fail("该漫画尚未下载")
        if not comic_manager.is_local_chapter(jm_id, chapter_id):
            return fail("章节不存在")
        chapters = comic_manager.get_comic_chapters(jm_id)
        target = next((ch for ch in chapters if ch["id"] == chapter_id), None)
        if not target:
            return fail("章节不存在")
        meta = comic_manager.get_comic_meta(jm_id) or {}
        return ok({
            "title": meta.get("title") or f"JM-{jm_id}",
            "chapters": chapters,
            "current_chapter": target["id"],
            "current_chapter_pages": target["pages"],
            "total_chapters": len(chapters),
        })
    except Exception as e:
        return fail(f"获取章节数据失败: {e}")


@bp.get("/api/comic/<int:jm_id>/page/<int:page_num>")
def api_comic_page(jm_id: int, page_num: int):
    try:
        chapter_id = request.args.get("chapter", None)
        # 轻量本地校验章节 id（不联网）：路径越界由 get_comic_page_path 的 realpath 兜底
        if not comic_manager.is_local_chapter(jm_id, chapter_id):
            return fail("章节不存在"), 400
        page_path = comic_manager.get_comic_page_path(jm_id, page_num, chapter_id)
        if page_path and os.path.exists(page_path):
            return send_file(page_path)
        return fail("页面不存在"), 404
    except Exception as e:
        return fail(str(e)), 500


@bp.post("/api/read/<int:jm_id>/progress")
def api_save_read_progress(jm_id: int):
    """保存阅读进度（0 基页码）。翻页时前端防抖上报。"""
    data = request.get_json(silent=True) or {}
    try:
        page = int(data.get("page") or 0)
    except (ValueError, TypeError):
        page = 0
    comic_manager.update_read_progress(jm_id, max(0, page))
    return jsonify({"success": True})


@bp.post("/api/status/<int:jm_id>/finished")
def api_status_finished(jm_id: int):
    """标记 / 取消「已读完」（阅读器翻到末章末尾自动调用）。

    读完 → 同时打回收标记（宽限 7 天后自动清本地，可重下）；取消读完 → 清标记。
    """
    on = bool((request.get_json(silent=True) or {}).get("finished", True))
    toggle_status_bit(jm_id, BIT_FINISHED, on)
    try:
        recycle_service.mark_finished(jm_id) if on else recycle_service.restore(jm_id)
    except Exception as e:
        log.warning("回收标记同步失败 %s: %s", jm_id, e)
    return jsonify({"success": True})
