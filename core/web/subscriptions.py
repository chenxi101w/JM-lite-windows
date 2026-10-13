# -*- coding: utf-8 -*-
"""订阅 API：订阅列表、更新推送、手动巡检、单作者作品列表。"""

from flask import Blueprint, request

from core.logging_setup import get_logger
from core.models.database import (
    clear_all_sub_updates,
    clear_subscription_new_count,
    delete_subscription,
    find_subscription_by_author,
    get_read_book_ids,
    get_sub_updates,
    get_subscriptions,
    mark_all_sub_updates_seen,
    mark_sub_update_seen,
    upsert_subscription,
)
from core.web.common import SUB_PAGE_AUTHOR_LIMIT, fail, get_jm_crawler, ok, sub_service

bp = Blueprint("subscriptions", __name__)
log = get_logger("subscription")


@bp.get("/api/subscriptions")
def api_subscriptions():
    try:
        return ok(get_subscriptions())
    except Exception as e:
        return fail(str(e))


@bp.post("/api/subscriptions")
def api_subscription_add():
    try:
        author = ((request.get_json(silent=True) or {}).get("author") or "").strip()
        if not author:
            return fail("author 不能为空")
        existing = find_subscription_by_author(author)
        if existing:
            return ok(None, id=existing["id"], exists=True)
        return ok(None, id=upsert_subscription(author))
    except Exception as e:
        return fail(str(e))


@bp.delete("/api/subscriptions/<int:sid>")
def api_subscription_delete(sid: int):
    try:
        delete_subscription(sid)
        return ok()
    except Exception as e:
        return fail(str(e))


@bp.post("/api/subscriptions/<int:sid>/clear-new")
def api_subscription_clear_new(sid: int):
    try:
        clear_subscription_new_count(sid)
        return ok()
    except Exception as e:
        return fail(str(e))


@bp.post("/api/subscriptions/poll")
def api_subscription_poll():
    """手动触发一次订阅巡检。"""
    try:
        return ok(None, **sub_service.poll_all(get_jm_crawler))
    except Exception as e:
        return fail(str(e))


@bp.get("/api/sub_updates")
def api_sub_updates():
    try:
        unseen = request.args.get("unseen") == "1"
        return ok(get_sub_updates(unseen_only=unseen))
    except Exception as e:
        return fail(str(e))


@bp.post("/api/sub_updates/seen")
def api_sub_updates_seen():
    try:
        data = request.get_json(silent=True) or {}
        if data.get("all"):
            mark_all_sub_updates_seen()
        else:
            book_id = data.get("book_id")
            if not book_id:
                return fail("book_id 或 all 必填")
            mark_sub_update_seen(int(book_id))
        return ok()
    except Exception as e:
        return fail(str(e))


@bp.delete("/api/sub_updates")
def api_sub_updates_clear():
    try:
        return ok(None, deleted=clear_all_sub_updates())
    except Exception as e:
        return fail(str(e))


@bp.get("/api/subscription-works")
def api_subscription_works():
    """订阅页：单个作者的全部作品。

    排序规则（用户需求）：未看的新作品在前、已看的老作品在后；两组内再分别按时间
    （JM 号越大越新）倒序。read 由本地 comic_status / downloaded_comics 判定。
    单作者搜索失败不抛 500，返回 error 字段由前端在对应区块提示，互不影响。
    """
    author = (request.args.get("author") or "").strip()
    if not author:
        return fail("author 必填")
    try:
        works = get_jm_crawler().search_by_author(author, max_total=SUB_PAGE_AUTHOR_LIMIT) or []
        ids = [int(c.get("id") or 0) for c in works if c.get("id")]
        read_set = get_read_book_ids(ids) if ids else set()
        out = [{
            "id": int(c.get("id") or 0),
            "title": c.get("title") or "",
            "author": c.get("author") or "",
            "cover": c.get("cover") or "",
            "read": int(c.get("id") or 0) in read_set,
        } for c in works]
        # 未看(0)在前、已看(1)在后；组内按 id 倒序（新→旧）
        out.sort(key=lambda x: (0 if not x["read"] else 1, -x["id"]))
        return ok(None, author=author, works=out)
    except Exception as e:
        log.warning("订阅作品拉取失败 %s: %s", author, e)
        return ok(None, author=author, works=[], error=str(e))
