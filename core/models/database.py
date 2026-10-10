# -*- coding: utf-8 -*-
"""数据库层 —— 建表、系统配置读写、漫画状态位。

发版铁律（继承旧版经验，务必遵守）：
- 建表一律 CREATE TABLE IF NOT EXISTS，幂等；
- 加列一律 ALTER TABLE ... ADD COLUMN 包 try/except，绝不 drop 重建清数据；
- 默认配置 INSERT OR IGNORE，保留用户已有值。
表随轻量目标精简：不含 search_history / reading_history / tag_library 系列。
"""

import json
import os
import re
import sqlite3
import threading

from core.config import DB_FILE

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """线程内单例连接（sqlite3 连接不可跨线程共享，按线程各持一份）。"""
    conn = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
        conn = sqlite3.connect(DB_FILE, timeout=15, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn


# ─── 建表 SQL ──────────────────────────────────────────────

DDL_CATEGORIES = """
CREATE TABLE IF NOT EXISTS categories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    parent_id  INTEGER DEFAULT NULL,
    sort_order INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE CASCADE
)
"""

DDL_DOWNLOADED_COMICS = """
CREATE TABLE IF NOT EXISTS downloaded_comics (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    jm_id        INTEGER UNIQUE NOT NULL,
    title        TEXT    NOT NULL,
    author       TEXT,
    tags         TEXT,
    description  TEXT,
    pages        INTEGER DEFAULT 0,
    chapter_count INTEGER DEFAULT 0,
    cover_path   TEXT,
    comic_path   TEXT,
    download_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_read_time DATETIME,
    read_progress INTEGER DEFAULT 0,
    file_size    INTEGER DEFAULT 0
)
"""

DDL_COMIC_CATEGORIES = """
CREATE TABLE IF NOT EXISTS comic_categories (
    comic_jm_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    PRIMARY KEY (comic_jm_id, category_id),
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
)
"""

DDL_DOWNLOAD_HISTORY = """
CREATE TABLE IF NOT EXISTS download_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    jm_id           INTEGER NOT NULL,
    title           TEXT NOT NULL,
    download_status TEXT NOT NULL,
    download_time   DATETIME DEFAULT CURRENT_TIMESTAMP,
    complete_time   DATETIME,
    error_message   TEXT
)
"""

DDL_SYSTEM_CONFIG = """
CREATE TABLE IF NOT EXISTS system_config (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    description TEXT,
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

DDL_BLOCKLIST = """
CREATE TABLE IF NOT EXISTS blocklist (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    block_type TEXT NOT NULL,
    value      TEXT NOT NULL,
    note       TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

DDL_ALIASES = """
CREATE TABLE IF NOT EXISTS aliases (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    type      TEXT NOT NULL,
    alias     TEXT NOT NULL UNIQUE,
    canonical TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

# 漫画关系状态登记表（位掩码，与旧版/Android 语义一致）。
# 主键 = jm 号；不随 downloaded_comics 级联删除：删本地只清 LOCAL 位，行保留。
# bit0 LOCAL / bit1 FINISHED / bit2 DOWNLOADED / bit3 FAVORITE / bit4 BLOCKED
DDL_COMIC_STATUS = """
CREATE TABLE IF NOT EXISTS comic_status (
    book_id      INTEGER PRIMARY KEY,
    status       INTEGER NOT NULL DEFAULT 0,
    title        TEXT    NOT NULL DEFAULT '',
    author       TEXT    NOT NULL DEFAULT '',
    cover_url    TEXT    NOT NULL DEFAULT '',
    tags         TEXT    NOT NULL DEFAULT '',
    view_count   INTEGER NOT NULL DEFAULT 0,
    last_read_at INTEGER NOT NULL DEFAULT 0,
    ext          TEXT    NOT NULL DEFAULT ''
)
"""

DDL_SUBSCRIPTIONS = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    author          TEXT    NOT NULL DEFAULT '',
    created_at      INTEGER NOT NULL DEFAULT 0,
    last_checked_at INTEGER NOT NULL DEFAULT 0,
    last_update_at  INTEGER NOT NULL DEFAULT 0,
    new_count       INTEGER NOT NULL DEFAULT 0,
    last_title      TEXT    NOT NULL DEFAULT ''
)
"""

DDL_SUB_UPDATES = """
CREATE TABLE IF NOT EXISTS sub_updates (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    author     TEXT    NOT NULL DEFAULT '',
    book_id    INTEGER NOT NULL DEFAULT 0,
    title      TEXT    NOT NULL DEFAULT '',
    cover_url  TEXT    NOT NULL DEFAULT '',
    found_at   INTEGER NOT NULL DEFAULT 0,
    seen       INTEGER NOT NULL DEFAULT 0
)
"""

ALL_DDL = [
    DDL_CATEGORIES,          # 先建 categories（comic_categories 有外键引用）
    DDL_DOWNLOADED_COMICS,
    DDL_COMIC_CATEGORIES,
    DDL_DOWNLOAD_HISTORY,
    DDL_SYSTEM_CONFIG,
    DDL_BLOCKLIST,
    DDL_ALIASES,
    DDL_COMIC_STATUS,
    DDL_SUBSCRIPTIONS,
    DDL_SUB_UPDATES,
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_comic_categories_cat ON comic_categories(category_id)",
    "CREATE INDEX IF NOT EXISTS idx_categories_parent ON categories(parent_id)",
    "CREATE INDEX IF NOT EXISTS idx_download_history_jm ON download_history(jm_id)",
    "CREATE INDEX IF NOT EXISTS idx_sub_updates_seen ON sub_updates(seen)",
    "CREATE INDEX IF NOT EXISTS idx_subscriptions_author ON subscriptions(author)",
    # 同一作品只登记一条新作记录（INSERT OR IGNORE 去重依赖它）
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_sub_updates_book ON sub_updates(book_id)",
]

# ─── comic_status 位常量 ───────────────────────────────────
BIT_LOCAL      = 1 << 0   # 1  在本地
BIT_FINISHED   = 1 << 1   # 2  已读完
BIT_DOWNLOADED = 1 << 2   # 4  已下载过（含删除）
BIT_FAVORITE   = 1 << 3   # 8  收藏
BIT_BLOCKED    = 1 << 4   # 16 拉黑（作品级）


def has_bit(status: int, bit: int) -> bool:
    return (status & bit) != 0


# ─── 默认配置（轻量集：其余历史开关不进默认表） ─────────────
DEFAULT_CONFIGS = [
    ("max_concurrent_downloads", "3", "最大并发下载数"),
    ("image_quality", "original", "图片质量"),
    ("theme", "system", "主题：system/light/dark"),
    ("theme_night_start", "22:00", "定时夜间起始时间（预留）"),
    ("theme_night_end", "06:00", "定时夜间结束时间（预留）"),
    ("proxy_enabled", "0", "启用代理下载 (0/1)"),
    ("proxy_url", "", "代理地址，如 http://127.0.0.1:7890"),
    ("search_result_limit", "80", "搜索结果上限"),
    ("default_sort", "mr", "搜索默认排序：mr=最新/mv=浏览量/mp=收藏量"),
    ("search_apply_blocks", "1", "搜索结果是否应用屏蔽规则（0/1）"),
    ("hide_downloaded_in_search", "hide", "搜索里已下载的漫画：off/hide/gray"),
    ("hide_finished_in_search", "hide", "搜索里已看完的漫画：off/hide/gray"),
    ("reader_chapter_toast", "1", "阅读器章节边界提醒（0/1）"),
    ("shelf_sort", "download_desc", "书架默认排序"),
    ("library_columns", "0", "书架每行列数（0=自动）"),
    ("search_columns", "0", "搜索结果每行列数（0=自动）"),
    ("library_finished", "divider", "书架已读完：divider=沉底+分隔线 / hidden=隐藏"),
    # ── 云同步（与手机端同服务器，预填地址与密钥；服务器只存 JM 号+时间戳）──
    ("sync_enabled", "0", "云同步开关（0/1）"),
    ("sync_server_url", "", "同步服务器地址"),
    ("sync_token", "", "同步密钥"),
    ("sync_last_at", "0", "上次同步成功时间(ms)"),
    ("sync_last_result", "", "上次同步结果文案"),
    # ── 阅读器滚轮行为 ──
    ("reader_wheel_mode", "zoom", "滚轮行为：zoom=以光标缩放 / scroll=上下滚动"),
]


# ─── 初始化 ────────────────────────────────────────────────

def init_database() -> None:
    """创建所有表并写入默认配置。幂等。"""
    conn = _get_conn()
    for ddl in ALL_DDL:
        conn.execute(ddl)
    for idx in INDEXES:
        conn.execute(idx)
    for key, value, desc in DEFAULT_CONFIGS:
        conn.execute(
            "INSERT OR IGNORE INTO system_config (key, value, description) VALUES (?, ?, ?)",
            (key, value, desc),
        )
    conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    """幂等加列：已存在则静默跳过，绝不 drop 重建（增量迁移用）。"""
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


# ─── 系统配置读写 ──────────────────────────────────────────

def get_system_config(key: str, default=None):
    row = _get_conn().execute(
        "SELECT value FROM system_config WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else default


def set_system_config(key: str, value: str, description: str = None) -> None:
    conn = _get_conn()
    if description is None:
        conn.execute(
            "INSERT INTO system_config (key, value, update_time) VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, update_time=CURRENT_TIMESTAMP",
            (key, value),
        )
    else:
        conn.execute(
            "INSERT INTO system_config (key, value, description, update_time) VALUES (?, ?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, update_time=CURRENT_TIMESTAMP",
            (key, value, description),
        )
    conn.commit()


def get_all_configs() -> dict:
    rows = _get_conn().execute("SELECT key, value FROM system_config").fetchall()
    return {r["key"]: r["value"] for r in rows}


# ─── comic_status 读写 ─────────────────────────────────────

def get_comic_status(jm_id: int) -> int:
    row = _get_conn().execute(
        "SELECT status FROM comic_status WHERE book_id = ?", (jm_id,)
    ).fetchone()
    return int(row["status"]) if row else 0


def set_comic_status(jm_id: int, status: int, **fields) -> None:
    """整值写入 status；fields 可带 title/author/cover_url/tags（upsert）。"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT book_id FROM comic_status WHERE book_id = ?", (jm_id,)
    ).fetchone()
    if row:
        sets = ["status = ?"]
        args = [int(status)]
        for k in ("title", "author", "cover_url", "tags"):
            if k in fields:
                sets.append(f"{k} = ?")
                args.append(fields[k] or "")
        args.append(jm_id)
        conn.execute(f"UPDATE comic_status SET {', '.join(sets)} WHERE book_id = ?", args)
    else:
        conn.execute(
            "INSERT INTO comic_status (book_id, status, title, author, cover_url, tags) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                jm_id,
                int(status),
                fields.get("title") or "",
                fields.get("author") or "",
                fields.get("cover_url") or "",
                fields.get("tags") or "",
            ),
        )
    conn.commit()


def toggle_status_bit(jm_id: int, bit: int, on: bool, **fields) -> int:
    """置/清某一位，返回新 status。"""
    status = get_comic_status(jm_id)
    new_status = (status | bit) if on else (status & ~bit)
    set_comic_status(jm_id, new_status, **fields)
    return new_status


# ─── 图片画质参数 ──────────────────────────────────────────

def get_image_quality_params() -> tuple:
    """根据 image_quality 设置返回 (quality, subsampling) 供 JPEG 保存使用。"""
    q = (get_system_config("image_quality") or "original").strip().lower()
    mapping = {
        "original": (100, 0),
        "high": (92, "keep"),
        "medium": (82, "keep"),
        "low": (65, "keep"),
    }
    return mapping.get(q, (100, 0))


# ─── 拉黑 / 别名 ───────────────────────────────────────────

def normalize_author(author: str) -> str:
    """作者名归一化：去空格、转小写、压缩连续空白，用于精确匹配。"""
    return re.sub(r"\s+", "", (author or "").strip().lower())


def get_blocks(block_type: str = None) -> list:
    conn = _get_conn()
    if block_type:
        return conn.execute(
            "SELECT id, block_type, value, note, created_at FROM blocklist WHERE block_type = ? ORDER BY id DESC",
            (block_type,),
        ).fetchall()
    return conn.execute(
        "SELECT id, block_type, value, note, created_at FROM blocklist ORDER BY id DESC"
    ).fetchall()


def get_blocked_sets() -> dict:
    """返回 {authors: set(归一化), works: set(int), tags: set(str)} 供搜索过滤使用。"""
    authors, works, tags = set(), set(), set()
    for r in get_blocks():
        if r["block_type"] == "author":
            authors.add(r["value"])
        elif r["block_type"] == "work":
            try:
                works.add(int(r["value"]))
            except (ValueError, TypeError):
                pass
        elif r["block_type"] == "tag":
            tags.add(r["value"])
    return {"authors": authors, "works": works, "tags": tags}


def add_block(block_type: str, value: str, note: str = None) -> int:
    """新增拉黑项。block_type='author'|'work'|'tag'；作者值自动归一化。返回新记录 id。"""
    if block_type not in ("author", "work", "tag"):
        raise ValueError("block_type 必须是 'author'、'work' 或 'tag'")
    if not value or not value.strip():
        raise ValueError("value 不能为空")
    val = normalize_author(value) if block_type == "author" else value.strip()
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO blocklist (block_type, value, note) VALUES (?, ?, ?)",
        (block_type, val, note),
    )
    conn.commit()
    return cur.lastrowid


def remove_block(block_id: int) -> bool:
    conn = _get_conn()
    cur = conn.execute("DELETE FROM blocklist WHERE id = ?", (block_id,))
    conn.commit()
    return cur.rowcount > 0


def get_aliases(type_: str) -> list:
    return _get_conn().execute(
        "SELECT alias, canonical FROM aliases WHERE type = ?", (type_,)
    ).fetchall()


def get_alias_map(type_: str) -> dict:
    """返回 {alias.lower(): canonical} 供搜索展开 / 展示归一化。"""
    m = {}
    for r in get_aliases(type_):
        m[r["alias"].lower()] = r["canonical"]
    return m


def upsert_alias(type_: str, alias: str, canonical: str) -> None:
    """幂等写入别名（alias 小写归一化，不覆盖已有）。"""
    alias = (alias or "").strip().lower()
    canonical = (canonical or "").strip()
    if not alias or not canonical:
        return
    conn = _get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO aliases (type, alias, canonical) VALUES (?, ?, ?)",
        (type_, alias, canonical),
    )
    conn.commit()


def set_status_bits(jm_id: int, *bits: int, clear: int = 0, **fields) -> int:
    """按位设置状态：先 OR 传入的 bits，再清掉 clear 里的位。返回新 status。"""
    status = get_comic_status(jm_id)
    for b in bits:
        status |= int(b)
    if clear:
        status &= ~int(clear)
    set_comic_status(jm_id, status, **fields)
    return status


# ─── 分类关联 ──────────────────────────────────────────────

def get_comic_categories(jm_id: int) -> list:
    rows = _get_conn().execute(
        "SELECT category_id FROM comic_categories WHERE comic_jm_id = ?", (jm_id,)
    ).fetchall()
    return [r["category_id"] for r in rows]


def get_all_comic_categories() -> dict:
    """{jm_id: [category_id, ...]} 一次取全，避免逐本查询。"""
    out: dict = {}
    for r in _get_conn().execute(
        "SELECT comic_jm_id, category_id FROM comic_categories"
    ).fetchall():
        out.setdefault(r["comic_jm_id"], []).append(r["category_id"])
    return out


def set_comic_categories(jm_id: int, category_ids: list) -> None:
    """整组替换某漫画的分类关联（去重、忽略非数字）。"""
    conn = _get_conn()
    conn.execute("DELETE FROM comic_categories WHERE comic_jm_id = ?", (jm_id,))
    seen = set()
    for cid in category_ids or []:
        try:
            cid = int(cid)
        except (ValueError, TypeError):
            continue
        if cid in seen:
            continue
        seen.add(cid)
        conn.execute(
            "INSERT OR IGNORE INTO comic_categories (comic_jm_id, category_id) VALUES (?, ?)",
            (jm_id, cid),
        )
    conn.commit()


# ─── 下载历史 ──────────────────────────────────────────────

def add_download_history(jm_id: int, title: str, status: str, error: str = None) -> None:
    conn = _get_conn()
    conn.execute(
        "INSERT INTO download_history (jm_id, title, download_status, complete_time, error_message) "
        "VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)",
        (jm_id, title, status, error),
    )
    conn.commit()


def get_download_history(limit: int = 50) -> list:
    rows = _get_conn().execute(
        "SELECT id, jm_id, title, download_status, download_time, complete_time, error_message "
        "FROM download_history ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_download_history(record_id: int) -> bool:
    conn = _get_conn()
    cur = conn.execute("DELETE FROM download_history WHERE id = ?", (record_id,))
    conn.commit()
    return cur.rowcount > 0


def clear_download_history() -> int:
    conn = _get_conn()
    cur = conn.execute("DELETE FROM download_history")
    conn.commit()
    return cur.rowcount


# ─── 分类（树） ────────────────────────────────────────────

def get_all_categories() -> list:
    """返回所有分类（平铺列表）。"""
    rows = _get_conn().execute(
        "SELECT id, name, parent_id, sort_order FROM categories ORDER BY sort_order, id"
    ).fetchall()
    return [dict(r) for r in rows]


def get_category_tree() -> list:
    """返回递归分类树（children 嵌套），每个节点附带漫画数量（含所有子孙分类）。"""
    from collections import defaultdict

    rows = get_all_categories()
    node_map: dict = {}
    roots: list = []
    children_map: dict = defaultdict(list)

    counts = {}
    for r in _get_conn().execute(
        "SELECT category_id, COUNT(*) as cnt FROM comic_categories GROUP BY category_id"
    ).fetchall():
        counts[r["category_id"]] = r["cnt"]

    for r in rows:
        node = {**r, "children": [], "count": counts.get(r["id"], 0)}
        node_map[r["id"]] = node
        children_map[r["parent_id"]].append(r["id"])

    # 自底向上递归求和：父节点 count = 直接归属数 + 各子节点累加（与 id 顺序无关）
    def _total(cid: int) -> int:
        s = node_map[cid]["count"]
        for ch in children_map.get(cid, []):
            s += _total(ch)
        node_map[cid]["count"] = s
        return s

    for cid in list(node_map.keys()):
        if node_map[cid]["parent_id"] not in node_map:
            _total(cid)
            roots.append(node_map[cid])

    for pid, children in children_map.items():
        if pid is not None and pid in node_map:
            for ch in children:
                node_map[pid]["children"].append(node_map[ch])

    def _sort(nodes: list) -> None:
        nodes.sort(key=lambda n: (n.get("sort_order", 0), n["id"]))
        for n in nodes:
            _sort(n["children"])

    _sort(roots)
    return roots


def create_category(name: str, parent_id=None) -> int:
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO categories (name, parent_id) VALUES (?, ?)", (name, parent_id)
    )
    conn.commit()
    return cur.lastrowid


def update_category(cat_id: int, name: str = None, parent_id=None) -> bool:
    fields, params = [], []
    if name is not None:
        fields.append("name = ?")
        params.append(name)
    if parent_id is not None:
        fields.append("parent_id = ?")
        params.append(parent_id)
    if not fields:
        return False
    params.append(cat_id)
    conn = _get_conn()
    conn.execute(f"UPDATE categories SET {', '.join(fields)} WHERE id = ?", params)
    conn.commit()
    return True


def set_category_parent(cat_id: int, parent_id) -> bool:
    """重定分类父级；parent_id 为 None 表示移到根目录。"""
    conn = _get_conn()
    conn.execute("UPDATE categories SET parent_id = ? WHERE id = ?", (parent_id, cat_id))
    conn.commit()
    return True


def _delete_category_row(conn, cat_id: int) -> bool:
    """真正执行删除：子分类提升到被删节点的父级，清残留关联，再删自身。"""
    row = conn.execute("SELECT parent_id FROM categories WHERE id = ?", (cat_id,)).fetchone()
    parent = row["parent_id"] if row else None
    conn.execute("UPDATE categories SET parent_id = ? WHERE parent_id = ?", (parent, cat_id))
    conn.execute("DELETE FROM comic_categories WHERE category_id = ?", (cat_id,))
    conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    conn.commit()
    return True


def delete_category(cat_id: int) -> bool:
    """删除分类（仅用于该分类下没有漫画的情况；非空应改调 delete_category_with_reassign）。"""
    if get_category_comic_count(cat_id) > 0:
        return False
    return _delete_category_row(_get_conn(), cat_id)


def get_category_comic_count(cat_id: int) -> int:
    """该分类直接归属的漫画数量（不含子分类）。"""
    row = _get_conn().execute(
        "SELECT COUNT(*) AS cnt FROM comic_categories WHERE category_id = ?", (cat_id,)
    ).fetchone()
    return int(row["cnt"]) if row else 0


def delete_category_with_reassign(cat_id: int, target_cat_id=None) -> bool:
    """删除分类并把它的漫画转移到目标分类。

    target_cat_id: 真实分类 id → 改归该分类；None → 移入「未归类」（删关联）。
    子分类一律提升为被删分类的父级，不随删除消失。
    """
    if target_cat_id is not None and target_cat_id == cat_id:
        return False
    conn = _get_conn()
    if not conn.execute("SELECT 1 FROM categories WHERE id = ?", (cat_id,)).fetchone():
        return False
    if target_cat_id is not None:
        if not conn.execute("SELECT 1 FROM categories WHERE id = ?", (target_cat_id,)).fetchone():
            return False
        # 先删目标关联再改，避免 PRIMARY KEY 冲突
        conn.execute(
            "DELETE FROM comic_categories WHERE category_id = ? AND comic_jm_id IN "
            "(SELECT comic_jm_id FROM comic_categories WHERE category_id = ?)",
            (target_cat_id, cat_id),
        )
        conn.execute(
            "UPDATE comic_categories SET category_id = ? WHERE category_id = ?",
            (target_cat_id, cat_id),
        )
    else:
        conn.execute("DELETE FROM comic_categories WHERE category_id = ?", (cat_id,))
    return _delete_category_row(conn, cat_id)


def get_category_descendant_ids(cat_id: int) -> list:
    """返回 cat_id 的所有后代分类 id（不含自身），用于环检测。"""
    rows = get_all_categories()
    by_parent: dict = {}
    for r in rows:
        by_parent.setdefault(r["parent_id"], []).append(r["id"])
    result = []
    stack = [cat_id]
    while stack:
        cur = stack.pop()
        for child in by_parent.get(cur, []):
            result.append(child)
            stack.append(child)
    return result


def get_comic_category(jm_id: int):
    """返回漫画所属的单个分类 id；未归类返回 None。"""
    row = _get_conn().execute(
        "SELECT category_id FROM comic_categories WHERE comic_jm_id = ? LIMIT 1", (jm_id,)
    ).fetchone()
    return row["category_id"] if row else None


# ─── 订阅（作者巡检） ──────────────────────────────────────

def _sub_row(row) -> dict:
    return {
        "id": row["id"], "author": row["author"],
        "created_at": row["created_at"], "last_checked_at": row["last_checked_at"],
        "last_update_at": row["last_update_at"], "new_count": row["new_count"],
        "last_title": row["last_title"],
    }


def get_subscriptions() -> list:
    """全部作者订阅，按订阅时间倒序。"""
    rows = _get_conn().execute(
        "SELECT * FROM subscriptions ORDER BY created_at DESC"
    ).fetchall()
    return [_sub_row(r) for r in rows]


def get_read_book_ids(ids: list) -> set:
    """给定 jm_id 列表，返回其中「已看 / 已在本地」的集合（订阅页排序用）。

    判定：出现在 downloaded_comics，或 comic_status 含 LOCAL / FINISHED / DOWNLOADED 位。
    """
    if not ids:
        return set()
    placeholders = ",".join("?" * len(ids))
    conn = _get_conn()
    read = set()
    try:
        rows = conn.execute(
            f"SELECT jm_id FROM downloaded_comics WHERE jm_id IN ({placeholders})", ids
        ).fetchall()
        for r in rows:
            read.add(r["jm_id"])
        srows = conn.execute(
            f"SELECT book_id, status FROM comic_status WHERE book_id IN ({placeholders})", ids
        ).fetchall()
        for r in srows:
            if int(r["status"] or 0) & (BIT_LOCAL | BIT_FINISHED | BIT_DOWNLOADED):
                read.add(r["book_id"])
    except Exception:
        pass
    return read


def find_subscription_by_author(author: str):
    """按作者名精确查找订阅；不存在返回 None。"""
    row = _get_conn().execute(
        "SELECT * FROM subscriptions WHERE author = ? LIMIT 1", (author,)
    ).fetchone()
    return _sub_row(row) if row else None


def upsert_subscription(author: str, created_at: int = None) -> int:
    """订阅作者（幂等）。返回 id。"""
    import time
    conn = _get_conn()
    if created_at is None:
        created_at = int(time.time() * 1000)
    conn.execute(
        "INSERT OR REPLACE INTO subscriptions (author, created_at) VALUES (?, ?)",
        (author, created_at),
    )
    conn.commit()
    row = conn.execute("SELECT id FROM subscriptions WHERE author = ?", (author,)).fetchone()
    return row["id"] if row else 0


def delete_subscription(sub_id: int) -> None:
    conn = _get_conn()
    conn.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
    conn.commit()


def note_subscription_checked(author: str, ts_ms: int) -> None:
    """订阅检查完毕：仅刷新 last_checked_at。"""
    conn = _get_conn()
    conn.execute(
        "UPDATE subscriptions SET last_checked_at = ? WHERE author = ?", (ts_ms, author)
    )
    conn.commit()


def note_subscription_update(author: str, ts_ms: int, delta: int, title: str) -> None:
    """订阅发现新作：刷新检查/更新时间，累加新作计数、记录最近新作标题。"""
    conn = _get_conn()
    conn.execute(
        "UPDATE subscriptions SET last_checked_at = ?, last_update_at = ?, "
        "new_count = new_count + ?, last_title = ? WHERE author = ?",
        (ts_ms, ts_ms, delta, title, author),
    )
    conn.commit()


def clear_subscription_new_count(sub_id: int) -> None:
    conn = _get_conn()
    conn.execute("UPDATE subscriptions SET new_count = 0 WHERE id = ?", (sub_id,))
    conn.commit()


# ─── 订阅新作记录（sub_updates）────────────────────────────

def _sub_update_row(row) -> dict:
    return {
        "id": row["id"], "author": row["author"], "book_id": row["book_id"],
        "title": row["title"], "cover_url": row["cover_url"],
        "found_at": row["found_at"], "seen": row["seen"],
    }


def get_sub_updates(*, unseen_only: bool = False) -> list:
    """订阅新作记录，按发现时间倒序。unseen_only=True 仅取未查看。"""
    sql = "SELECT * FROM sub_updates"
    if unseen_only:
        sql += " WHERE seen = 0"
    sql += " ORDER BY found_at DESC"
    rows = _get_conn().execute(sql).fetchall()
    return [_sub_update_row(r) for r in rows]


def get_sub_updates_by_author(author: str) -> list:
    rows = _get_conn().execute(
        "SELECT * FROM sub_updates WHERE author = ? ORDER BY found_at DESC", (author,)
    ).fetchall()
    return [_sub_update_row(r) for r in rows]


def insert_sub_update(author: str, book_id: int = 0, title: str = "",
                      cover_url: str = "", found_at: int = None, *,
                      ignore_duplicate: bool = True) -> None:
    """记录一条新作（同 book_id 已存在则忽略，防重复）。"""
    import time
    conn = _get_conn()
    if found_at is None:
        found_at = int(time.time() * 1000)
    sql = ("INSERT OR IGNORE INTO sub_updates (author, book_id, title, cover_url, found_at) "
           "VALUES (?, ?, ?, ?, ?)") if ignore_duplicate else \
          ("INSERT INTO sub_updates (author, book_id, title, cover_url, found_at) "
           "VALUES (?, ?, ?, ?, ?)")
    conn.execute(sql, (author, book_id, title, cover_url, found_at))
    conn.commit()


def mark_sub_update_seen(book_id: int) -> None:
    conn = _get_conn()
    conn.execute("UPDATE sub_updates SET seen = 1 WHERE book_id = ?", (book_id,))
    conn.commit()


def mark_all_sub_updates_seen() -> None:
    conn = _get_conn()
    conn.execute("UPDATE sub_updates SET seen = 1")
    conn.commit()


def delete_sub_updates_by_author(author: str) -> None:
    conn = _get_conn()
    conn.execute("DELETE FROM sub_updates WHERE author = ?", (author,))
    conn.commit()


def clear_all_sub_updates() -> int:
    conn = _get_conn()
    cur = conn.execute("DELETE FROM sub_updates")
    conn.commit()
    return cur.rowcount


# ─── 黑名单管理 ────────────────────────────────────────────

def list_blocklist() -> list:
    """黑名单全量（按类型分组由前端处理），按创建时间倒序。"""
    return [dict(r) for r in get_blocks()]


# ─── 看过入账 / 回收站（ext JSON，零 DDL） ────────────────

def get_comic_status_row(jm_id: int):
    """账本行全量（含 title/author/cover_url/tags/ext）；不存在返回 None。"""
    row = _get_conn().execute(
        "SELECT * FROM comic_status WHERE book_id = ?", (jm_id,)
    ).fetchone()
    return dict(row) if row else None


def get_all_status_ids() -> list:
    """账本全部 JM 号（「看过」全集，云同步 push 用）。"""
    rows = _get_conn().execute("SELECT book_id FROM comic_status").fetchall()
    return [int(r["book_id"]) for r in rows]


def get_favorite_ids() -> list:
    """所有已收藏的 JM 号（BIT_FAVORITE 位，收藏备份导出用）。"""
    rows = _get_conn().execute(
        "SELECT book_id FROM comic_status WHERE (status & ?) != 0",
        (BIT_FAVORITE,),
    ).fetchall()
    return [int(r["book_id"]) for r in rows]


def touch_comic_status(jm_id: int, **fields) -> None:
    """「看过」入账：确保账本行存在（不改任何状态位）。

    - 无行 → 建最小行（status=0 + 可用元数据）；
    - 有行 → 仅补齐当前为空的 title/author/cover_url/tags，绝不覆盖已有值。
    """
    row = get_comic_status_row(jm_id)
    if row is None:
        set_comic_status(
            jm_id, 0,
            title=fields.get("title"), author=fields.get("author"),
            cover_url=fields.get("cover_url"), tags=fields.get("tags"),
        )
        return
    updates = {}
    for k in ("title", "author", "cover_url", "tags"):
        v = fields.get(k)
        if v and not str(row.get(k) or "").strip():
            updates[k] = v
    if updates:
        set_comic_status(jm_id, int(row["status"]), **updates)


def _read_ext(ext_str: str) -> dict:
    try:
        d = json.loads(ext_str or "{}")
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def get_recycle_mark(jm_id: int) -> int:
    """回收站标记时间(ms)；未标记返回 0。"""
    row = get_comic_status_row(jm_id)
    if not row:
        return 0
    try:
        return int(_read_ext(row.get("ext") or "").get("recycle_at") or 0)
    except Exception:
        return 0


def set_recycle_mark(jm_id: int, ts_ms: int = None) -> None:
    """写/清回收站标记（ext.recycle_at）。ts_ms 为空表示清除标记。"""
    conn = _get_conn()
    row = get_comic_status_row(jm_id)
    if row is None:
        return
    ext = _read_ext(row.get("ext") or "")
    if ts_ms:
        ext["recycle_at"] = int(ts_ms)
    else:
        ext.pop("recycle_at", None)
    conn.execute(
        "UPDATE comic_status SET ext = ? WHERE book_id = ?",
        (json.dumps(ext, ensure_ascii=False) if ext else "", jm_id),
    )
    conn.commit()


def list_recycled() -> list:
    """回收站列表：所有带 recycle_at 标记的账本行（按标记时间倒序）。"""
    rows = _get_conn().execute(
        "SELECT book_id, status, title, author, cover_url, tags, last_read_at, ext "
        "FROM comic_status WHERE ext LIKE '%recycle_at%'"
    ).fetchall()
    out = []
    for r in rows:
        try:
            ts = int(_read_ext(r["ext"]).get("recycle_at") or 0)
        except Exception:
            ts = 0
        if ts <= 0:
            continue
        out.append({
            "id": int(r["book_id"]),
            "status": int(r["status"]),
            "title": r["title"] or "",
            "author": r["author"] or "",
            "cover_url": r["cover_url"] or "",
            "tags": r["tags"] or "",
            "last_read_at": int(r["last_read_at"] or 0),
            "recycle_at": ts,
        })
    out.sort(key=lambda x: x["recycle_at"], reverse=True)
    return out