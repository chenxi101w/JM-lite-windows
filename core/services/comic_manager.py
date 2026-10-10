# -*- coding: utf-8 -*-
"""漫画管理器 —— 已下载漫画的管理、阅读、分类（轻量版）。

从旧版搬改：保留本地索引（O(n²) 优化）、章节扫描、页面路径（含越界防御）、
阅读进度；去掉回收站（轻量版删即删）。
"""

import json
import os
import re
import shutil
from typing import Dict, List, Optional

# 性能：jmcomic 惰性 import（仅阅读器章节顺序需要时加载）

from core.config import BASE_DIR, DOWNLOAD_DIR
from core.models.database import (
    BIT_FAVORITE,
    BIT_FINISHED,
    BIT_LOCAL,
    _get_conn,
    get_all_comic_categories,
    set_status_bits,
)


class ComicManager:
    """本地漫画生命周期管理。"""

    # 目录索引做成类级共享缓存：下载流程会在另一个 ComicManager 实例里写库并
    # invalidate，只有共享缓存才能让主实例立即看到新下载的漫画。
    _index_cache: Optional[Dict[int, str]] = None

    def __init__(self):
        self.base_dir = BASE_DIR
        self.downloaded_dir = DOWNLOAD_DIR
        os.makedirs(self.downloaded_dir, exist_ok=True)
        # 章节顺序联网取一次即缓存：本地阅读不应对 JM 在线状态有依赖（离线也能读）
        self._chapter_order_cache: Dict[int, Optional[List[str]]] = {}

    # ─── 路径 / 图片辅助 ───────────────────────────────────

    def _build_index(self) -> Dict[int, str]:
        """单次 listdir 建立 jm_id -> 漫画目录索引，替代每本漫画全目录扫描的 O(n²) 行为。"""
        idx: Dict[int, str] = {}
        try:
            for name in os.listdir(self.downloaded_dir):
                if "_" not in name:
                    continue
                try:
                    jid = int(name.split("_", 1)[0])
                except ValueError:
                    continue
                idx[jid] = os.path.join(self.downloaded_dir, name)
        except OSError:
            pass
        return idx

    def _get_index(self) -> Dict[int, str]:
        if ComicManager._index_cache is None:
            ComicManager._index_cache = self._build_index()
        return ComicManager._index_cache

    def _invalidate_index(self) -> None:
        ComicManager._index_cache = None

    def _find_downloaded_dir(self, jm_id: int) -> Optional[str]:
        idx = self._get_index()
        found = idx.get(jm_id)
        if found:
            return found
        # 缓存可能过期（如下载由另一实例完成），主动重建一次
        self._invalidate_index()
        return self._get_index().get(jm_id)

    def _comic_already_finalized(self, jm_id: int) -> bool:
        return self._find_downloaded_dir(jm_id) is not None

    def _collect_images_recursive(self, root: str) -> List[str]:
        """递归收集目录下所有图片（排除封面），按自然顺序返回完整路径列表。"""
        exts = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}
        files = []
        for dp, _, fns in os.walk(root):
            for fn in fns:
                if os.path.splitext(fn)[1].lower() in exts and not fn.lower().startswith("cover"):
                    files.append(os.path.join(dp, fn))

        def _nat(p: str):
            return [int(s) if s.isdigit() else s for s in re.split(r"(\d+)", p)]

        files.sort(key=_nat)
        return files

    def _scan_chapters_in_dir(self, root: str) -> List[Dict]:
        """扫描单个漫画根目录（平铺页面或分章子目录），返回章节列表。"""
        if not root or not os.path.isdir(root):
            return []
        exts = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}
        chapters: List[Dict] = []
        subdirs = [d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))]
        if subdirs:
            def _sk(d):
                try:
                    return int(d)
                except ValueError:
                    return d

            ordered = sorted(subdirs, key=_sk)
            idx = 0
            for sub in ordered:
                sp = os.path.join(root, sub)
                pages = sum(
                    1 for f in os.listdir(sp)
                    if os.path.splitext(f)[1].lower() in exts and not f.lower().startswith("cover")
                )
                if pages > 0:
                    idx += 1
                    chapters.append({
                        "id": sub, "name": f"第{idx}章",
                        "pages": list(range(1, pages + 1)), "path": sp, "index": idx - 1,
                    })
        else:
            page_count = sum(
                1 for f in os.listdir(root)
                if os.path.splitext(f)[1].lower() in exts and not f.lower().startswith("cover")
            )
            if page_count > 0:
                chapters.append({
                    "id": "1", "name": "第1章",
                    "pages": list(range(1, page_count + 1)), "path": root, "index": 0,
                })
        return chapters

    # ─── 数据库操作 ────────────────────────────────────────

    def is_comic_downloaded(self, jm_id: int) -> bool:
        conn = _get_conn()
        row = conn.execute("SELECT id FROM downloaded_comics WHERE jm_id = ?", (jm_id,)).fetchone()
        return bool(row and jm_id in self._get_index())

    def add_downloaded_comic(self, jm_id: int, comic_info: dict) -> bool:
        conn = _get_conn()
        try:
            comic_dir = self._find_downloaded_dir(jm_id)
            if not comic_dir:
                return False

            cover_path = None
            if os.path.exists(os.path.join(comic_dir, "cover.jpg")):
                cover_path = os.path.join(comic_dir, "cover.jpg")

            file_size = 0
            try:
                for root, _, files in os.walk(comic_dir):
                    for f in files:
                        fp = os.path.join(root, f)
                        if os.path.isfile(fp):
                            file_size += os.path.getsize(fp)
            except Exception:
                pass

            chapter_count = len(self.get_comic_chapters(jm_id))
            page_count = len(self._collect_images_recursive(comic_dir))

            conn.execute(
                """INSERT OR REPLACE INTO downloaded_comics
                   (jm_id, title, author, tags, description, pages, chapter_count,
                    cover_path, comic_path, file_size)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    jm_id,
                    comic_info.get("title", ""),
                    comic_info.get("author", ""),
                    ",".join(comic_info.get("tags", [])),
                    comic_info.get("description", ""),
                    page_count,
                    chapter_count,
                    cover_path,
                    None,
                    file_size,
                ),
            )
            conn.commit()
            self._invalidate_index()
            # 本地内容已重建 → 置 LOCAL 位；若在回收站则自动拾回（清标记）
            set_status_bits(jm_id, BIT_LOCAL, title=comic_info.get("title", ""),
                            author=comic_info.get("author", ""))
            try:
                from core.models.database import set_recycle_mark
                set_recycle_mark(jm_id, None)
            except Exception:
                pass
            return True
        except Exception as e:
            print(f"添加已下载漫画失败 {jm_id}: {e}")
            return False

    # 书架排序白名单（键 → ORDER BY 片段；键值来自系统配置 shelf_sort，防注入）
    SHELF_ORDERS = {
        "download_desc": "d.download_time DESC",
        "read_desc": "CASE WHEN d.last_read_time IS NULL OR d.last_read_time = '' "
                     "THEN 1 ELSE 0 END, d.last_read_time DESC, d.download_time DESC",
        "title_asc": "d.title ASC",
        "author_asc": "d.author ASC, d.title ASC",
    }

    def get_downloaded_comics(self, category_id: Optional[int] = None,
                              uncategorized: bool = False,
                              sort: str = "download_desc") -> List[Dict]:
        """获取已下载漫画列表（分类筛选 / 未归类）。收藏与读完状态来自 comic_status。

        sort：书架排序（download_desc 最新下载 / read_desc 最近阅读 /
        title_asc 标题 / author_asc 作者），非法值回落最新下载。
        """
        conn = _get_conn()
        _cols = ("d.jm_id, d.title, d.author, d.tags, d.pages, d.chapter_count, "
                 "d.download_time, d.last_read_time, d.read_progress, d.file_size")
        order = self.SHELF_ORDERS.get(sort or "", self.SHELF_ORDERS["download_desc"])
        if uncategorized:
            query = f"""SELECT {_cols}
                       FROM downloaded_comics d
                       WHERE NOT EXISTS (
                           SELECT 1 FROM comic_categories cc WHERE cc.comic_jm_id = d.jm_id
                       )
                       ORDER BY {order}"""
            rows = conn.execute(query).fetchall()
        elif category_id is not None:
            query = f"""SELECT {_cols}
                       FROM downloaded_comics d
                       INNER JOIN comic_categories cc ON d.jm_id = cc.comic_jm_id
                       WHERE cc.category_id = ?
                       ORDER BY {order}"""
            rows = conn.execute(query, (category_id,)).fetchall()
        else:
            query = f"""SELECT {_cols}
                       FROM downloaded_comics d ORDER BY {order}"""
            rows = conn.execute(query).fetchall()

        # 单次 listdir 建索引 + 批量取分类与状态，避免逐本扫描/查询
        index = self._get_index()
        all_cats = get_all_comic_categories()
        status_map = {}
        for r in conn.execute("SELECT book_id, status FROM comic_status").fetchall():
            status_map[int(r["book_id"])] = int(r["status"])

        comics = []
        for row in rows:
            jm_id = row["jm_id"]
            comic_dir = index.get(jm_id)
            if not comic_dir:
                continue

            cover_path = None
            if os.path.exists(os.path.join(comic_dir, "cover.jpg")):
                cover_path = os.path.join(comic_dir, "cover.jpg")

            # 历史数据 pages=0 时按本地图片文件修复一次并回写
            pages = row["pages"]
            if not pages or pages <= 0:
                try:
                    pages = len(self._collect_images_recursive(comic_dir))
                    if pages > 0:
                        conn.execute(
                            "UPDATE downloaded_comics SET pages = ? WHERE jm_id = ?",
                            (pages, jm_id),
                        )
                        conn.commit()
                except Exception:
                    pages = row["pages"] or 0

            st = status_map.get(jm_id, 0)
            comics.append({
                "id": jm_id,
                "title": row["title"],
                "author": row["author"],
                "tags": row["tags"].split(",") if row["tags"] else [],
                "pages": pages,
                "chapter_count": row["chapter_count"] or 0,
                "cover_path": cover_path,
                "download_time": row["download_time"],
                "last_read_time": row["last_read_time"],
                "read_progress": row["read_progress"],
                "file_size": row["file_size"],
                "category_ids": all_cats.get(jm_id, []),
                "favorite": 1 if (st & BIT_FAVORITE) else 0,
                "finished": 1 if (st & BIT_FINISHED) else 0,
            })
        return comics

    def get_comic_meta(self, jm_id: int) -> Optional[Dict]:
        """单本已下载漫画的元信息（一次 DB 查询 + 索引直取）。未下载返回 None。"""
        conn = _get_conn()
        row = conn.execute(
            "SELECT title, author, tags, description, pages, chapter_count, file_size "
            "FROM downloaded_comics WHERE jm_id = ?",
            (jm_id,),
        ).fetchone()
        if not row:
            return None
        comic_dir = self._find_downloaded_dir(jm_id)
        if not comic_dir:
            return None
        cover_path = None
        if os.path.exists(os.path.join(comic_dir, "cover.jpg")):
            cover_path = os.path.join(comic_dir, "cover.jpg")
        return {
            "id": jm_id,
            "title": row["title"],
            "author": row["author"],
            "tags": row["tags"].split(",") if row["tags"] else [],
            "description": row["description"] or "",
            "pages": row["pages"] or 0,
            "chapter_count": row["chapter_count"] or 0,
            "cover_path": cover_path,
            "file_size": row["file_size"],
        }

    def get_read_progress(self, jm_id: int) -> int:
        """该本最近阅读到的页码（0 = 从没读过）。"""
        row = _get_conn().execute(
            "SELECT read_progress FROM downloaded_comics WHERE jm_id = ?", (jm_id,)
        ).fetchone()
        return int(row["read_progress"] or 0) if row else 0

    def update_read_progress(self, jm_id: int, page_num: int) -> None:
        conn = _get_conn()
        conn.execute(
            "UPDATE downloaded_comics SET last_read_time = CURRENT_TIMESTAMP, read_progress = ? "
            "WHERE jm_id = ?",
            (page_num, jm_id),
        )
        conn.commit()

    # ─── 章节 / 页面 ──────────────────────────────────────

    def _get_chapter_order_from_jm(self, jm_id: int, use_cache: bool = True) -> Optional[List[str]]:
        """章节顺序联网取一次并缓存；JM 不可达时回落本地顺序（离线可读）。"""
        if use_cache and jm_id in self._chapter_order_cache:
            return self._chapter_order_cache[jm_id]
        try:
            import jmcomic
            client = jmcomic.JmOption.default().new_jm_client()
            album = client.get_album_detail(jm_id)
            order = [str(p.photo_id) for p in album]
        except Exception as e:
            print(f"从JM获取章节顺序失败 {jm_id}: {e}")
            order = None
        if use_cache:
            self._chapter_order_cache[jm_id] = order
        return order

    def is_local_chapter(self, jm_id: int, chapter_id: Optional[str]) -> bool:
        """轻量本地校验章节 id（不联网）：单章用 '1'；多章必须是漫画根目录下真实子目录名。"""
        if not chapter_id:
            return True
        if ".." in chapter_id or "/" in chapter_id or "\\" in chapter_id or os.path.sep in chapter_id:
            return False
        comic_dir = self._find_downloaded_dir(jm_id)
        if not comic_dir:
            return False
        if chapter_id == "1":
            return True
        return os.path.isdir(os.path.join(comic_dir, chapter_id))

    def get_comic_chapters(self, jm_id: int) -> List[Dict]:
        comic_dir = self._find_downloaded_dir(jm_id)
        if comic_dir:
            chapters = self._scan_chapters_in_dir(comic_dir)
            if chapters and len(chapters) > 1:
                chapter_order = self._get_chapter_order_from_jm(jm_id)
                if chapter_order:
                    by_id = {c["id"]: c for c in chapters}
                    ordered = []
                    for oid in chapter_order:
                        c = by_id.pop(oid, None)
                        if c:
                            ordered.append(c)
                    ordered += list(by_id.values())
                    for i, c in enumerate(ordered):
                        c["index"] = i
                        c["name"] = f"第{i + 1}章"
                    chapters = ordered
            if chapters:
                return chapters

        # 兜底：临时下载目录（下载未完成最终搬运、页面滞留 TempCache 时也能阅读）
        temp = os.path.join(self.base_dir, "TempCache", "downloads", str(jm_id))
        if os.path.isdir(temp):
            imgs = self._collect_images_recursive(temp)
            if imgs:
                return [{
                    "id": "1", "name": "第1章",
                    "pages": list(range(1, len(imgs) + 1)), "path": temp, "index": 0,
                }]
        return []

    def get_comic_page_path(self, jm_id: int, page_num: int,
                            chapter_id: Optional[str] = None) -> Optional[str]:
        comic_dir = self._find_downloaded_dir(jm_id)
        if not comic_dir:
            temp = os.path.join(self.base_dir, "TempCache", "downloads", str(jm_id))
            if os.path.isdir(temp):
                comic_dir = temp
        if not comic_dir:
            return None

        # 捕获越界校验基准（章节重定向前的真实根目录）
        confine_base = comic_dir

        if chapter_id:
            # 拒绝任何路径元字符，防止目录跳出（纵深防御，API 层已先校验）
            if ".." in chapter_id or "/" in chapter_id or "\\" in chapter_id or os.path.sep in chapter_id:
                return None
            chapter_path = os.path.join(comic_dir, chapter_id)
            if os.path.isdir(chapter_path):
                comic_dir = chapter_path

        # 最终落盘前再次确认路径不越出漫画根目录（防符号链接/相对路径逃逸）
        resolved = os.path.realpath(comic_dir)
        base = os.path.realpath(confine_base)
        if not (resolved == base or resolved.startswith(base + os.sep)):
            return None

        candidates = [
            f"{page_num:05d}.jpg", f"{page_num:05d}.png",
            f"{page_num:04d}.jpg", f"{page_num:04d}.png",
            f"{page_num:03d}.jpg", f"{page_num:03d}.png",
            f"{page_num:02d}.jpg", f"{page_num:02d}.png",
            f"{page_num}.jpg", f"{page_num}.png",
        ]
        for fname in candidates:
            path = os.path.join(comic_dir, fname)
            if os.path.exists(path):
                return path

        exts = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}
        indexed = []
        for fname in os.listdir(comic_dir):
            ext = os.path.splitext(fname)[1].lower()
            if ext in exts:
                digits = "".join(filter(str.isdigit, os.path.splitext(fname)[0]))
                if digits:
                    indexed.append((int(digits), fname))
        indexed.sort()
        for num, fname in indexed:
            if num == page_num:
                return os.path.join(comic_dir, fname)

        # 递归兜底：兼容 TempCache 中 {Aid}/{Pid}/图片 的嵌套结构
        imgs = self._collect_images_recursive(comic_dir)
        if 1 <= page_num <= len(imgs):
            return imgs[page_num - 1]
        return None

    # ─── 删除（轻量版：删即删） ────────────────────────────

    def delete_completely(self, jm_id: int) -> bool:
        """彻底删除：记录 + 分类关联 + 本地内容全清；清 LOCAL 位（行保留在 comic_status）。"""
        try:
            conn = _get_conn()
            conn.execute("DELETE FROM downloaded_comics WHERE jm_id = ?", (jm_id,))
            conn.execute("DELETE FROM comic_categories WHERE comic_jm_id = ?", (jm_id,))
            conn.commit()
            comic_dir = self._find_downloaded_dir(jm_id)
            if comic_dir:
                shutil.rmtree(comic_dir, ignore_errors=True)
            self._invalidate_index()
            set_status_bits(jm_id, clear=BIT_LOCAL)
            return True
        except Exception as e:
            print(f"彻底删除漫画失败 {jm_id}: {e}")
            return False

    def delete_comic(self, jm_id: int) -> bool:
        return self.delete_completely(jm_id)

    def get_cache_size(self) -> int:
        total = 0
        try:
            for dirpath, _, filenames in os.walk(self.downloaded_dir):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if os.path.isfile(fp):
                        total += os.path.getsize(fp)
        except Exception:
            pass
        return total