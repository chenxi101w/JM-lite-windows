# -*- coding: utf-8 -*-
"""书架域 API：已下载列表、封面服务、删除/回收站、收藏备份、分类、黑名单。"""

import json
import os
import time
from datetime import datetime
from typing import Dict

from flask import Blueprint, current_app, jsonify, request, send_file

from core.config import BASE_DIR, STATIC_DIR, TEMP_CACHE_DIR
from core.logging_setup import get_logger
from core.models.database import (
    BIT_FAVORITE,
    _get_conn,
    get_blocked_sets,
    get_comic_status,
    get_system_config,
    has_bit,
    normalize_author,
    set_comic_categories,
    toggle_status_bit,
)
from core.services import recycle as recycle_service
from core.web.common import comic_manager, fail, get_jm_crawler, ok

bp = Blueprint("library", __name__)
log = get_logger("library")


# ── 已下载列表 ─────────────────────────────────────────────

@bp.get("/api/downloaded")
def api_downloaded():
    """已下载漫画列表。?category_id=N / ?uncategorized=1 筛选；排序取设置 shelf_sort。"""
    try:
        sort = get_system_config("shelf_sort") or "download_desc"
        comics = comic_manager.get_downloaded_comics(
            category_id=request.args.get("category_id", type=int),
            uncategorized=request.args.get("uncategorized") == "1",
            sort=sort,
        )
        # 标注是否被拉黑（作者/作品），供前端书架灰显
        blocked = get_blocked_sets()
        for c in comics:
            c["blocked"] = bool(
                c.get("id") in blocked["works"]
                or (c.get("author") and normalize_author(c.get("author")) in blocked["authors"])
            )
        return ok(comics)
    except Exception as e:
        return fail(f"获取列表失败: {e}")


# ── 封面服务 ───────────────────────────────────────────────

# 封面失败负缓存：拉不到的本在 TTL 内直接返回占位图（避免每次页面加载都做
# 6~8 个域 × 6s 的全轮询——单张失败要 7s+，整页封面会被拖垮）
_COVER_FAIL_TTL = 600
_cover_fail_until: Dict[int, float] = {}
_NO_COVER_PATH = os.path.join(STATIC_DIR, "img", "no_cover.svg")


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
    except OSError:
        pass
    return "image/jpeg"


def _send_no_cover():
    """封面兜底占位图（200，前端 img 永不破图）。"""
    return send_file(_NO_COVER_PATH, mimetype="image/svg+xml")


def _serve_cover(jm_id: int):
    """封面统一出口：缓存 → 负缓存 → 实时拉取 → 占位图兜底。

    拉取成功时：落 TempCache 缓存 + **顺手补书目录 cover.jpg**（历史缺封面的
    已下载本自愈）。任何失败路径都返回占位图，绝不让前端出现破图。
    """
    cache_path = os.path.join(TEMP_CACHE_DIR, f"cover_{jm_id}.jpg")
    try:
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
            return send_file(cache_path, mimetype=_cover_mimetype(cache_path))
    except OSError:
        pass
    if _cover_fail_until.get(jm_id, 0) > time.time():
        return _send_no_cover()
    try:
        crawler = get_jm_crawler()
        data = crawler.fetch_cover_bytes(jm_id, crawler.get_cover_url(jm_id))
        if data:
            tmp = cache_path + ".tmp"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, cache_path)
            _cover_fail_until.pop(jm_id, None)
            _repair_local_cover(jm_id, data)
            return send_file(cache_path, mimetype=_cover_mimetype(cache_path))
    except Exception as e:
        log.warning("封面拉取失败 %s: %s", jm_id, e)
    _cover_fail_until[jm_id] = time.time() + _COVER_FAIL_TTL
    return _send_no_cover()


def _repair_local_cover(jm_id: int, data: bytes) -> None:
    """书目录自愈：该本已在库但缺 cover.jpg 时补齐。"""
    try:
        d = comic_manager._find_downloaded_dir(jm_id)
        if d and not os.path.exists(os.path.join(d, "cover.jpg")):
            with open(os.path.join(d, "cover.jpg"), "wb") as f:
                f.write(data)
    except Exception as e:
        log.debug("本地封面自愈失败 %s: %s", jm_id, e)


@bp.get("/api/cover/proxy/<int:jm_id>")
def api_cover_proxy(jm_id: int):
    """远程封面的本地代理（服务端拉取 + 磁盘缓存 + 占位兜底）。"""
    return _serve_cover(jm_id)


@bp.get("/api/cover/downloaded/<int:jm_id>")
def api_cover_downloaded(jm_id: int):
    """本地已下载漫画的封面图：书目录 cover.jpg → 缓存 → 实时拉取(自愈) → 占位。"""
    try:
        comic_dir = comic_manager._find_downloaded_dir(jm_id)
        if comic_dir:
            cover = os.path.join(comic_dir, "cover.jpg")
            if os.path.exists(cover):
                return send_file(cover)
    except Exception as e:
        log.debug("本地封面读取失败 %s: %s", jm_id, e)
    return _serve_cover(jm_id)


# ── 删除 / 回收站 ──────────────────────────────────────────

@bp.delete("/api/delete/<int:jm_id>")
def api_delete_comic(jm_id: int):
    """删除本地 = 移入回收站（保留账本与封面，宽限 7 天，可重新下载恢复）。"""
    try:
        done = recycle_service.trash_local(jm_id, comic_manager)
        return jsonify({"success": done, "message": "已移入回收站" if done else "删除失败"})
    except Exception as e:
        return fail(str(e))


@bp.get("/api/recycle")
def api_recycle_list():
    try:
        # 打开回收站时顺手做一次到期检查（宽限已过的标记项清本地内容）
        recycle_service.purge_expired(comic_manager)
        return ok(recycle_service.list_for_ui(comic_manager),
                  grace_days=recycle_service.RECYCLE_GRACE_DAYS)
    except Exception as e:
        return fail(str(e))


@bp.post("/api/recycle/<int:jm_id>/restore")
def api_recycle_restore(jm_id: int):
    try:
        return jsonify({"success": recycle_service.restore(jm_id)})
    except Exception as e:
        return fail(str(e))


@bp.delete("/api/recycle/<int:jm_id>")
def api_recycle_purge(jm_id: int):
    """彻底删除（不可恢复）。"""
    try:
        return jsonify({"success": recycle_service.purge_one(jm_id, comic_manager)})
    except Exception as e:
        return fail(str(e))


@bp.post("/api/status/<int:jm_id>/favorite")
def api_status_favorite(jm_id: int):
    """收藏 / 取消收藏。"""
    on = bool((request.get_json(silent=True) or {}).get("favorite", True))
    toggle_status_bit(jm_id, BIT_FAVORITE, on)
    return jsonify({"success": True})


# ── 收藏备份（导出 / 导入，格式兼容手机端「JM 轻量版」）──────

def _favorites_payload() -> Dict:
    """构造收藏备份 JSON（零网络：detail_cache → 已下载表补元数据）。"""
    from core.models.database import get_favorite_ids

    ids = get_favorite_ids()
    dcache = getattr(get_jm_crawler(), "detail_cache", {}) or {}
    meta: Dict[int, Dict] = {}
    if ids:
        try:
            marks = ",".join("?" for _ in ids)
            for r in _get_conn().execute(
                f"SELECT jm_id, title, author FROM downloaded_comics WHERE jm_id IN ({marks})",
                ids
            ).fetchall():
                meta[int(r["jm_id"])] = {"title": r["title"], "author": r["author"]}
        except Exception as e:
            log.warning("收藏元数据兜底查询失败: %s", e)

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


@bp.post("/api/favorites/export")
def api_favorites_export():
    """导出收藏到 UserData/exports/（JSON，兼容手机端收藏备份，可跨端导入）。"""
    try:
        payload = _favorites_payload()
        export_dir = os.path.join(BASE_DIR, "UserData", "exports")
        os.makedirs(export_dir, exist_ok=True)
        path = os.path.join(export_dir, "jm_lite_favorites_%s.json"
                            % datetime.now().strftime("%Y%m%d_%H%M%S"))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return ok({"path": path, "count": len(payload["favoriteBooks"])})
    except Exception as e:
        return fail(f"导出失败: {e}")


@bp.get("/api/favorites/export")
def api_favorites_export_raw():
    """导出收藏 JSON（浏览器直接下载用；桌面 UI 走 POST 写文件）。"""
    body = json.dumps(_favorites_payload(), ensure_ascii=False, indent=2)
    filename = "jm_lite_favorites_%s.json" % datetime.now().strftime("%Y%m%d")
    return current_app.response_class(
        body, mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=%s" % filename},
    )


@bp.post("/api/favorites/import")
def api_favorites_import():
    """导入收藏备份（兼容手机端导出；已收藏的幂等跳过）。"""
    try:
        books = (request.get_json(silent=True) or {}).get("favoriteBooks")
        if not isinstance(books, list):
            return fail("不是有效的收藏备份（缺少 favoriteBooks）")
        added = 0
        for item in books:
            try:
                jm_id = int((item or {}).get("id") or 0)
            except (TypeError, ValueError):
                continue
            if jm_id <= 0 or has_bit(get_comic_status(jm_id), BIT_FAVORITE):
                continue
            toggle_status_bit(jm_id, BIT_FAVORITE, True)
            added += 1
        return ok({"total": len(books), "added": added})
    except Exception as e:
        return fail(f"导入失败: {e}")


# ── 分类 ───────────────────────────────────────────────────

@bp.get("/api/categories")
def api_categories():
    """分类列表。?tree=1 返回树形结构。"""
    from core.models.database import get_all_categories, get_category_tree
    return ok(get_category_tree() if request.args.get("tree", "0") == "1" else get_all_categories())


@bp.post("/api/categories")
def api_category_create():
    from core.models.database import create_category
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return fail("分类名称不能为空")
    try:
        return ok({"id": create_category(name, data.get("parent_id")), "name": name})
    except Exception as e:
        return fail(f"创建失败: {e}")


@bp.put("/api/categories/<int:cat_id>")
def api_category_update(cat_id: int):
    from core.models.database import update_category
    data = request.get_json(silent=True) or {}
    if update_category(cat_id, name=data.get("name"), parent_id=data.get("parent_id")):
        return ok()
    return fail("更新失败")


@bp.get("/api/categories/<int:cat_id>")
@bp.delete("/api/categories/<int:cat_id>")
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
        return fail("仅支持 DELETE 或 ?count_only=1")

    data = request.get_json(silent=True) or {}
    raw = data.get("reassign_to", "__absent__")
    target = None
    if raw not in ("__absent__", None, "", "null"):
        try:
            target = int(raw)
        except (ValueError, TypeError):
            return fail("reassign_to 无效")

    cnt = get_category_comic_count(cat_id)
    if cnt > 0:
        if "reassign_to" not in data:
            return fail(f"该分类下有 {cnt} 部漫画，请先选择将它们移动到哪个分类",
                        need_reassign=True, count=cnt)
        done = delete_category_with_reassign(cat_id, target)
    else:
        done = delete_category(cat_id)
    if done:
        return ok(None, count=cnt)
    return fail("删除失败（分类不存在或目标分类无效）")


@bp.post("/api/categories/<int:cat_id>/move")
def api_category_move(cat_id: int):
    """移动分类（重定父级）。阻止移到自身或其子孙下，避免成环。"""
    from core.models.database import get_category_descendant_ids, set_category_parent
    raw_parent = (request.get_json(silent=True) or {}).get("parent_id")
    parent_id = None
    if raw_parent is not None and str(raw_parent) != "" and str(raw_parent).lower() != "null":
        try:
            parent_id = int(raw_parent)
        except (ValueError, TypeError):
            return fail("parent_id 无效")
    if parent_id is not None:
        if parent_id == cat_id:
            return fail("不能移动到自身")
        if parent_id in get_category_descendant_ids(cat_id):
            return fail("不能移动到其子分类下")
    if set_category_parent(cat_id, parent_id):
        return ok()
    return fail("移动失败")


@bp.get("/api/comic/<int:jm_id>/categories")
def api_comic_categories_get(jm_id: int):
    from core.models.database import get_comic_categories
    return ok(get_comic_categories(jm_id))


@bp.put("/api/comic/<int:jm_id>/categories")
def api_comic_categories_set(jm_id: int):
    data = request.get_json(silent=True) or {}
    set_comic_categories(jm_id, [int(c) for c in data.get("category_ids", []) if str(c).isdigit()])
    return jsonify({"success": True})


# ── 黑名单 ─────────────────────────────────────────────────

@bp.get("/api/blocklist")
def api_blocklist():
    from core.models.database import list_blocklist
    try:
        return ok(list_blocklist())
    except Exception as e:
        return fail(str(e))


@bp.post("/api/blocklist")
def api_blocklist_add():
    from core.models.database import add_block
    try:
        data = request.get_json(silent=True) or {}
        btype = (data.get("type") or "").strip()
        value = (data.get("value") or "").strip()
        if btype not in ("author", "work", "tag"):
            return fail("type 必须是 author/work/tag")
        if not value:
            return fail("value 不能为空")
        return ok(None, id=add_block(btype, value))
    except Exception as e:
        return fail(str(e))


@bp.delete("/api/blocklist/<int:block_id>")
def api_blocklist_delete(block_id: int):
    from core.models.database import remove_block
    try:
        return jsonify({"success": remove_block(block_id)})
    except Exception as e:
        return fail(str(e))
