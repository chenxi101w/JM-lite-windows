# -*- coding: utf-8 -*-
"""订阅巡检服务 —— 按作者检查新作。

从旧版 core/app.py 抽出为独立模块：
- poll_all(): 巡检一次所有订阅作者，把发现的新作写入 sub_updates
- schedule(): 启动后延迟 3 分钟首检，此后每小时一次（daemon Timer，进程退出即停）
"""

import threading
import time

from core.models.database import (
    get_sub_updates_by_author,
    get_subscriptions,
    insert_sub_update,
    note_subscription_checked,
    note_subscription_update,
)
from core.services.filter_service import expand_author

SUB_POLL_INTERVAL_SECONDS = 3600   # 正式间隔 1 小时
SUB_POLL_START_DELAY = 180         # 启动后 3 分钟首次巡检（等网络/代理就绪）
SUB_POLL_AUTHOR_LIMIT = 30         # 每次巡检单作者最多拉取条数


def poll_all(jm_crawler) -> dict:
    # 兼容传入惰性 getter（callable）：首次巡检时才真正构造 JMCrawler
    crawler = jm_crawler() if callable(jm_crawler) else jm_crawler
    """按作者巡检一次订阅，返回 {checked, added_new, authors_with_new}。

    单作者新作判定：取 search_by_author() 前 N 条，过滤掉 sub_updates 中已存在
    book_id 的条目，任何新 id 都算首次发现的新作（避免 JM 时间字段不稳定导致漏报）。
    """
    try:
        subs = get_subscriptions()
    except Exception as e:
        print(f"[SubPoll] 读订阅列表失败: {e}")
        return {"checked": 0, "added_new": 0, "authors_with_new": 0, "error": str(e)}

    checked = 0
    added_new = 0
    authors_with_new = 0
    now_ms = int(time.time() * 1000)

    for s in subs:
        author = (s.get("author") or "").strip()
        if not author:
            continue
        try:
            # 同义作者展开，避免别名作者漏更
            try:
                expanded = expand_author(author) or [author]
            except Exception:
                expanded = [author]
            collected = []
            seen_ids = set()
            for a in expanded:
                try:
                    res = crawler.search_by_author(a, max_total=SUB_POLL_AUTHOR_LIMIT) or []
                except Exception as e2:
                    print(f"[SubPoll] 作者搜索异常 '{a}': {e2}")
                    continue
                for c in res:
                    cid = int(c.get("id") or 0)
                    if not cid or cid in seen_ids:
                        continue
                    seen_ids.add(cid)
                    collected.append(c)
            if not collected:
                note_subscription_checked(author, now_ms)
                checked += 1
                continue

            # 已有 sub_updates 中的 book_id 去重
            try:
                existing_updates = get_sub_updates_by_author(author) or []
            except Exception:
                existing_updates = []
            known_ids = {int(u.get("book_id") or 0) for u in existing_updates if u.get("book_id")}
            new_items = [c for c in collected if int(c.get("id") or 0) not in known_ids]
            new_items.sort(key=lambda c: int(c.get("id") or 0))

            delta = 0
            last_title = ""
            for c in new_items:
                cid = int(c.get("id") or 0)
                title = (c.get("title") or "").strip() or f"作品 {cid}"
                cover_url = (c.get("cover") or "").strip()
                try:
                    insert_sub_update(author=author, book_id=cid, title=title,
                                      cover_url=cover_url, found_at=now_ms,
                                      ignore_duplicate=True)
                except Exception as ie:
                    print(f"[SubPoll] 插入新作记录失败 '{author}' id={cid}: {ie}")
                    continue
                delta += 1
                last_title = title
                added_new += 1

            if delta > 0:
                note_subscription_update(author, now_ms, delta, last_title)
                authors_with_new += 1
            else:
                note_subscription_checked(author, now_ms)
            checked += 1
        except Exception as e:
            print(f"[SubPoll] 巡检作者 '{author}' 失败: {e}")
            continue

    summary = {"checked": checked, "added_new": added_new, "authors_with_new": authors_with_new}
    if added_new:
        print(f"[SubPoll] 巡检完成：检查 {checked} 位作者，新增 {added_new} 条新作（{authors_with_new} 位有更新）")
    else:
        print(f"[SubPoll] 巡检完成：检查 {checked} 位作者，无新增。")
    return summary


def schedule(jm_crawler) -> None:
    """启动延迟 3 分钟首次巡检 → 每 60 分钟一次。daemon Timer，进程退出即停。"""
    def _run():
        try:
            crawler = jm_crawler() if callable(jm_crawler) else jm_crawler
            poll_all(crawler)
        except Exception as e:
            print(f"[SubPoll] 例行巡检异常: {e}")
        finally:
            t = threading.Timer(SUB_POLL_INTERVAL_SECONDS, _run)
            t.daemon = True
            t.start()

    t0 = threading.Timer(SUB_POLL_START_DELAY, _run)
    t0.daemon = True
    t0.start()