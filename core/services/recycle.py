# -*- coding: utf-8 -*-
"""回收站服务 —— 宽限保留、到期清本地、恢复 / 重下 / 彻底删除（对齐手机端）。

语义（账本行 = 真相源；标记存 comic_status.ext.recycle_at，零 DDL）：
- **删除本地**（书架 🗑）→ 立即删文件 + 清 downloaded 行，打回收标记 → 进回收站，可重新下载恢复；
- **看完** → 打回收标记（宽限 7 天）：期内本地保留可继续读，重读自动续期；
- **到期检查**（启动 + 打开回收站时）→ 删本地内容（保留账本 + 标记 + 封面）→ 留在回收站待重下；
- **恢复** → 清标记（内容还在=直接回书架；已删=留账本，重下后回书架）；
- **彻底删除** → 删账本行 + 标记 + 残留内容/封面，不可恢复。
"""

import os
import shutil
import time

from core.config import TEMP_CACHE_DIR
from core.models.database import (
    BIT_LOCAL,
    get_comic_status,
    get_comic_status_row,
    get_recycle_mark,
    has_bit,
    list_recycled,
    set_recycle_mark,
    set_status_bits,
    _get_conn,
)

RECYCLE_GRACE_DAYS = 7
_GRACE_MS = RECYCLE_GRACE_DAYS * 24 * 60 * 60 * 1000


def _cover_cache_path(jm_id: int) -> str:
    return os.path.join(TEMP_CACHE_DIR, f"cover_{jm_id}.jpg")


def keep_cover(jm_id: int, comic_dir: str) -> None:
    """把本地封面复制到缓存（回收站条目仍能显示封面）。"""
    try:
        src = os.path.join(comic_dir, "cover.jpg")
        dst = _cover_cache_path(jm_id)
        if os.path.exists(src) and not os.path.exists(dst):
            os.makedirs(TEMP_CACHE_DIR, exist_ok=True)
            shutil.copy2(src, dst)
    except Exception as e:
        print(f"保留封面失败 {jm_id}: {e}")


def _delete_local_only(jm_id: int, comic_manager) -> None:
    """删本地文件 + downloaded 行 + 清 LOCAL 位（账本行保留）。"""
    comic_dir = comic_manager._find_downloaded_dir(jm_id)
    if comic_dir:
        keep_cover(jm_id, comic_dir)
    conn = _get_conn()
    conn.execute("DELETE FROM downloaded_comics WHERE jm_id = ?", (jm_id,))
    conn.commit()
    if comic_dir and os.path.isdir(comic_dir):
        shutil.rmtree(comic_dir, ignore_errors=True)
    comic_manager._invalidate_index()
    set_status_bits(jm_id, clear=BIT_LOCAL)


def trash_local(jm_id: int, comic_manager) -> bool:
    """书架「删除」= 移入回收站：删本地内容 + 打标记（可重下恢复）。"""
    try:
        if get_comic_status_row(jm_id) is None:
            # 理论上不会有（下载即入账），兜底建行以承载标记
            set_status_bits(jm_id, BIT_LOCAL)
        _delete_local_only(jm_id, comic_manager)
        set_recycle_mark(jm_id, int(time.time() * 1000))
        return True
    except Exception as e:
        print(f"移入回收站失败 {jm_id}: {e}")
        return False


def mark_finished(jm_id: int) -> None:
    """看完 → 打回收标记（宽限期后自动清本地）。"""
    try:
        set_recycle_mark(jm_id, int(time.time() * 1000))
    except Exception as e:
        print(f"看完入回收标记失败 {jm_id}: {e}")


def renew(jm_id: int) -> None:
    """重新阅读 → 续期宽限（重置标记时间）。"""
    try:
        if get_recycle_mark(jm_id) > 0:
            set_recycle_mark(jm_id, int(time.time() * 1000))
    except Exception:
        pass


def restore(jm_id: int) -> bool:
    """恢复：清除回收标记（内容在=回书架；已删=留账本待重下）。"""
    try:
        set_recycle_mark(jm_id, None)
        return True
    except Exception as e:
        print(f"恢复失败 {jm_id}: {e}")
        return False


def purge_one(jm_id: int, comic_manager) -> bool:
    """彻底删除：账本行 + 标记 + 残留内容/封面全清，不可恢复。"""
    try:
        comic_dir = comic_manager._find_downloaded_dir(jm_id)
        if comic_dir and os.path.isdir(comic_dir):
            shutil.rmtree(comic_dir, ignore_errors=True)
        comic_manager._invalidate_index()
        conn = _get_conn()
        conn.execute("DELETE FROM downloaded_comics WHERE jm_id = ?", (jm_id,))
        conn.execute("DELETE FROM comic_categories WHERE comic_jm_id = ?", (jm_id,))
        conn.execute("DELETE FROM comic_status WHERE book_id = ?", (jm_id,))
        conn.commit()
        try:
            if os.path.exists(_cover_cache_path(jm_id)):
                os.remove(_cover_cache_path(jm_id))
        except Exception:
            pass
        return True
    except Exception as e:
        print(f"彻底删除失败 {jm_id}: {e}")
        return False


def purge_expired(comic_manager) -> int:
    """到期检查：宽限期已过且本地仍在的标记项 → 删本地内容（保留账本+封面+标记）。"""
    now = int(time.time() * 1000)
    purged = 0
    for item in list_recycled():
        jm_id = item["id"]
        if now <= item["recycle_at"] + _GRACE_MS:
            continue
        status = get_comic_status(jm_id)
        if not has_bit(status, BIT_LOCAL):
            continue  # 本地已不在，无需处理
        try:
            _delete_local_only(jm_id, comic_manager)
            purged += 1
            print(f"[Recycle] 宽限到期，已清除本地内容：{jm_id}")
        except Exception as e:
            print(f"[Recycle] 到期清理失败 {jm_id}: {e}")
    return purged


def list_for_ui(comic_manager) -> list:
    """回收站列表（含本地是否仍在 + 剩余天数），供前端展示。"""
    now = int(time.time() * 1000)
    out = []
    for item in list_recycled():
        jm_id = item["id"]
        status = get_comic_status(jm_id)
        local = has_bit(status, BIT_LOCAL)
        remain = max(0, (item["recycle_at"] + _GRACE_MS - now + 24 * 3600 * 1000 - 1) // (24 * 3600 * 1000))
        out.append({
            **item,
            "local": bool(local),
            "remain_days": int(remain) if local else 0,
        })
    return out