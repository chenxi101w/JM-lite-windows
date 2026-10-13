# -*- coding: utf-8 -*-
"""过滤与别名服务 —— 拉黑过滤 + 标签/作者别名展开与归一化。

- postprocess_results(): 搜索结果后处理（剔除拉黑项 + 标签/作者归一化到 canonical）。
- expand_tags() / expand_author(): 把用户输入的标签/作者展开为其同义词组，供搜索时一并检索。
  （此功能为硬需求：同义词扩展必须长期保留）
- ensure_aliases_seeded(): 把内置种子同义词幂等写入 aliases 表，让展开开箱即用。
"""

from typing import Dict, List

from core.models.database import (
    get_alias_map,
    get_blocked_sets,
    normalize_author,
    upsert_alias,
)
from core.logging_setup import get_logger

log = get_logger("filter_service")

# 内置种子同义词（canonical 在前，其余为别名）。启动时幂等入库。
SEED_SYNONYMS: Dict[str, List] = {
    "tag": [
        ("巨乳", ["爆乳", "巨乳", "大奶"]),
        ("JK", ["女子高生", "女学生", "JK"]),
        ("单篇", ["单话", "短篇", "单篇"]),
        ("中文", ["汉化", "中文翻译", "中文"]),
        ("无修正", ["无修", "无修正版", "无修正"]),
        ("性转", ["性轉", "性转"]),
        ("调教", ["调教", "凌辱", "调教系"]),
    ],
    "author": [],
}


def ensure_aliases_seeded() -> None:
    """把种子同义词幂等写入 aliases 表（已存在的不覆盖）。"""
    try:
        for type_, seeds in SEED_SYNONYMS.items():
            for canon, aliases in seeds:
                for a in aliases:
                    a = (a or "").strip()
                    if a and a != canon:
                        upsert_alias(type_, a, canon)
    except Exception as e:
        log.warning(f"种子同义词入库失败: {e}")


def postprocess_results(results: List[dict]) -> List[dict]:
    """过滤拉黑项 + 标签/作者归一化到 canonical。

    results: list[dict]，每个含 id / author / tags。原地修改并返回同一列表。
    """
    if not results:
        return results or []
    blocked = get_blocked_sets()
    tag_map = get_alias_map("tag")
    author_map = get_alias_map("author")
    blocked_tags = blocked.get("tags", set())
    out: List[dict] = []
    for c in results:
        if not isinstance(c, dict):
            continue
        aid = c.get("id")
        author = c.get("author") or ""
        # ── 拉黑过滤 ──
        if aid is not None and aid in blocked["works"]:
            continue
        if author and normalize_author(author) in blocked["authors"]:
            continue
        tags = c.get("tags") or []
        if isinstance(tags, str):
            tags = [t for t in tags.split(",") if t.strip()]
        if blocked_tags and any((t or "").strip() in blocked_tags for t in tags):
            continue
        # ── 标签归一化 ──
        new_tags: List[str] = []
        for t in tags:
            tt = (t or "").strip()
            if not tt:
                continue
            canon = tag_map.get(tt.lower(), tt)
            if canon not in new_tags:
                new_tags.append(canon)
        c["tags"] = new_tags
        # ── 作者归一化 ──
        if author and author_map.get(author.lower()):
            c["author"] = author_map[author.lower()]
        out.append(c)
    return out


def _reverse_alias_map(alias_map: Dict[str, str]) -> Dict[str, List[str]]:
    """canonical -> [aliases]。"""
    rev: Dict[str, List[str]] = {}
    for alias, canon in alias_map.items():
        rev.setdefault(canon, [])
        if alias != canon.lower():
            rev[canon].append(alias)
    return rev


def expand_tags(tags: List[str]) -> List[str]:
    """把每个标签展开为 canonical + 其全部别名。去重，canonical 在前。"""
    tag_map = get_alias_map("tag")
    rev = _reverse_alias_map(tag_map)
    out: List[str] = []
    seen = set()
    for t in tags:
        tt = (t or "").strip()
        if not tt:
            continue
        canon = tag_map.get(tt.lower(), tt)
        for variant in [canon] + rev.get(canon, []):
            if variant and variant not in seen:
                seen.add(variant)
                out.append(variant)
    return out


def expand_author(author: str) -> List[str]:
    """把作者展开为 canonical + 其全部别名。去重。"""
    if not author or not author.strip():
        return []
    author_map = get_alias_map("author")
    canon = author_map.get(author.strip().lower(), author.strip())
    aliases = [a for a, c in author_map.items() if c == canon]
    out: List[str] = []
    seen = set()
    for v in [canon] + aliases:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out