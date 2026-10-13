# -*- coding: utf-8 -*-
"""搜索相关 API（JM 号 / 关键词 / 标签 / 作者 / 详情补充）与结果后处理。"""

from typing import Dict, List

from flask import Blueprint, request

from core.logging_setup import get_logger
from core.models.database import (
    BIT_FAVORITE,
    BIT_FINISHED,
    BIT_LOCAL,
    _get_conn,
    get_blocked_sets,
    get_system_config,
    has_bit,
    normalize_author,
)
from core.services.filter_service import expand_author, expand_tags, postprocess_results
from core.web.common import cfg_bool, cfg_int, fail, get_jm_crawler, ok

bp = Blueprint("search", __name__)
log = get_logger("search")


# ── 结果后处理 ─────────────────────────────────────────────

def _filter_blocked(results: List[Dict]) -> List[Dict]:
    """剔除已拉黑的作品 / 作者 / 标签（所有搜索入口统一过滤）。"""
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
        if any(str(t) in blocked["tags"] for t in (c.get("tags") or [])):
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
    except Exception as e:
        log.warning("本地状态批量查询失败: %s", e)
    return out


def _enrich_and_filter_search(results: List[Dict]) -> List[Dict]:
    """搜索结果后处理：黑名单过滤 + 附加本地状态 + 按设置隐藏已下/已读完。"""
    if not results:
        return results or []

    if cfg_bool("search_apply_blocks", True):
        results = _filter_blocked(results)

    ids = []
    for c in results:
        try:
            ids.append(int(c.get("id") or 0))
        except (TypeError, ValueError):
            pass
    local_map = _local_status_map(ids)

    mode_dl = (get_system_config("hide_downloaded_in_search") or "hide").strip().lower()
    mode_fin = (get_system_config("hide_finished_in_search") or "hide").strip().lower()

    out = []
    for c in results:
        try:
            jid = int(c.get("id") or 0)
        except (TypeError, ValueError):
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


# ── 端点 ───────────────────────────────────────────────────

@bp.get("/api/search/jm/<int:jm_id>")
@bp.get("/api/detail/<int:jm_id>")
def search_by_jm_id(jm_id: int):
    """JM 号搜索 / 详情模态数据（同源）。"""
    try:
        info = get_jm_crawler().get_comic_info(jm_id)
        if not info:
            return fail("未找到对应的漫画")
        blocked = get_blocked_sets()
        cid = info.get("id")
        if (cid is not None and cid in blocked["works"]) or (
            info.get("author") and normalize_author(info.get("author")) in blocked["authors"]
        ):
            return fail("该作品已被屏蔽")
        # 「看过」入账（云同步账本）：打开详情即算看过
        try:
            from core.models.database import touch_comic_status
            tags = info.get("tags")
            touch_comic_status(
                jm_id,
                title=info.get("title"), author=info.get("author"),
                cover_url=info.get("cover"),
                tags=",".join(tags) if isinstance(tags, list) else tags,
            )
        except Exception as e:
            log.debug("看过入账失败 %s: %s", jm_id, e)
        return ok(info)
    except Exception as e:
        return fail(f"搜索失败: {e}")


@bp.get("/api/cover/<int:jm_id>")
def api_cover(jm_id: int):
    """封面 URL（本地构造，无网络请求）。"""
    try:
        url = get_jm_crawler().get_cover_url(jm_id)
        return ok({"id": jm_id, "cover": url}, success=bool(url))
    except Exception as e:
        return fail(str(e))


@bp.get("/api/search/keyword")
def api_search_keyword():
    keyword = request.args.get("keyword", "").strip()
    if not keyword:
        return fail("关键词不能为空")
    sort_order = request.args.get("sort", "desc")
    order_by = request.args.get("order_by", "") or _default_order_by()
    time_range = request.args.get("time", "a")
    try:
        page_num = max(1, int(request.args.get("page", "1").strip()))
        results = get_jm_crawler().search_by_keyword(
            keyword, sort_order, page=page_num, order_by=order_by, time_range=time_range,
        )
        results = _enrich_and_filter_search(postprocess_results(results))
        return ok(results, order_by=order_by)
    except Exception as e:
        return fail(f"搜索失败: {e}")


@bp.get("/api/search/tags")
def api_search_tags():
    tags = request.args.get("tags", "").strip()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    if not tag_list:
        return fail("请选择至少一个标签")
    try:
        limit = cfg_int("search_result_limit", 80)
        mode = request.args.get("mode", "or").strip().lower()
        if mode not in ("or", "and"):
            mode = "or"
        # 别名展开：每个标签一并检索其同义词；命中用户实际输入名的排前面
        results, stats = get_jm_crawler().search_by_tags(
            expand_tags(tag_list), mode=mode, max_total=limit, input_tags=tag_list,
        )
        results = _enrich_and_filter_search(postprocess_results(results))
        return ok(results, stats=stats)
    except Exception as e:
        return fail(f"搜索失败: {e}")


@bp.get("/api/search/author")
def api_search_author():
    author = request.args.get("author", "").strip()
    if not author:
        return fail("作者不能为空")
    try:
        limit = cfg_int("search_result_limit", 80)
        # 别名展开：作者名一并检索其同义署名
        results, seen = [], set()
        for a in expand_author(author):
            for c in get_jm_crawler().search_by_author(a, max_total=limit):
                if c.get("id") not in seen:
                    seen.add(c.get("id"))
                    results.append(c)
        results = _enrich_and_filter_search(postprocess_results(results))
        return ok(results, author=author)
    except Exception as e:
        return fail(f"搜索失败: {e}")


@bp.get("/api/search/enrich")
def api_search_enrich():
    """批量补充卡片详情（标签等），供前端对可见卡片按需调用。"""
    ids_param = request.args.get("ids", "").strip()
    if not ids_param:
        return fail("缺少 ids 参数")
    album_ids = [int(r) for r in (raw.strip() for raw in ids_param.split(",")) if r.isdigit()][:12]
    if not album_ids:
        return fail("没有可用的 ids")
    try:
        return ok(get_jm_crawler().get_search_result_details(album_ids))
    except Exception as e:
        return fail(f"补充详情失败: {e}")
