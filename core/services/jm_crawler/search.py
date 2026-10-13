# -*- coding: utf-8 -*-
"""搜索（自 jm_crawler.py 拆出）。

关键词 / 标签 / 作者搜索、同义词展开、搜索结果详情批量抓取。"""

import concurrent.futures
import copy
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from core.logging_setup import get_logger

log = get_logger("jm_crawler")

class SearchMixin:
    """关键词 / 标签 / 作者搜索与同义词展开。"""
    def _extract_search_result(self, album) -> Optional[Dict]:
        comic_info = {}

        if isinstance(album, tuple) and len(album) >= 2:
            album_id = album[0]
            info_dict = album[1]
            # jmcomic search_tag 返回的是 (album_id, title) 二元组
            if isinstance(info_dict, str):
                comic_info = {
                    "id": int(album_id) if album_id and str(album_id).isdigit() else 0,
                    "title": info_dict or "未知标题",
                    "author": "",
                    "cover": "",
                    "favorites": 0,
                    "tags": [],
                    "description": "",
                }
            elif isinstance(info_dict, dict):
                favorites_raw = 0
                for key in ("favorites", "likes", "like", "favourites", "favorite", "fav"):
                    if key in info_dict and info_dict[key] is not None:
                        favorites_raw = info_dict[key]
                        break
                comic_info = {
                    "id": int(album_id) if album_id and str(album_id).isdigit() else 0,
                    "title": info_dict.get("name", "未知标题"),
                    "author": info_dict.get("author", "未知作者"),
                    "cover": "",
                    "favorites": self._parse_count(favorites_raw),
                    "tags": list(info_dict.get("tags", []) or []),
                    "description": (info_dict.get("description") or "")[:100],
                }
            else:
                return None
        elif hasattr(album, "__dict__"):
            favorites_raw = (
                getattr(album, "favorites", None)
                if getattr(album, "favorites", None) is not None
                else getattr(album, "likes", 0)
            )
            comic_info = {
                "id": getattr(album, "id", 0),
                "title": getattr(album, "title", None) or getattr(album, "name", "未知标题"),
                "author": getattr(album, "author", "未知作者"),
                "cover": "",
                "favorites": self._parse_count(favorites_raw),
                "tags": list(getattr(album, "tags", []) or []),
                "description": (getattr(album, "description", None) or "")[:100],
            }
        elif isinstance(album, dict):
            favorites_raw = 0
            for key in ("favorites", "likes", "like", "favourites", "favorite", "fav"):
                if key in album and album[key] is not None:
                    favorites_raw = album[key]
                    break
            comic_info = {
                "id": album.get("id", 0),
                "title": album.get("name", album.get("title", "未知标题")),
                "author": album.get("author", "未知作者"),
                "cover": "",
                "favorites": self._parse_count(favorites_raw),
                "tags": list(album.get("tags", []) or []),
                "description": (album.get("description") or "")[:100],
            }

        if not comic_info or not comic_info.get("id"):
            return None

        comic_info["needs_cover"] = True
        comic_info["needs_detail"] = True
        return comic_info

    def _fetch_search_detail(self, client, album_id: int) -> Optional[Dict]:
        try:
            detail = client.get_album_detail(album_id)
            if not detail:
                return None
            return {
                "id": album_id,
                "title": str(getattr(detail, "title", "") or getattr(detail, "name", "未知标题")),
                "favorites": self._parse_count(getattr(detail, "likes", 0)),
                "author": str(getattr(detail, "author", "未知作者")),
                "tags": list(getattr(detail, "tags", []) or []),
                "description": (getattr(detail, "description", None) or "")[:100],
                "pages": getattr(detail, "page_count", 0),
            }
        except Exception as e:
            log.warning(f"获取搜索详情失败 {album_id}: {e}")
            return None

    def get_search_result_details(self, album_ids: List[int]) -> Dict[str, Dict]:
        cleaned_ids = []
        seen_ids = set()
        for album_id in album_ids:
            try:
                parsed_id = int(album_id)
            except (TypeError, ValueError):
                continue
            if parsed_id <= 0 or parsed_id in seen_ids:
                continue
            seen_ids.add(parsed_id)
            cleaned_ids.append(parsed_id)
        if not cleaned_ids:
            return {}

        details = {}
        # 命中本地详情缓存的先直接取，避免重复网络请求
        missing = []
        for album_id in cleaned_ids:
            with self._detail_cache_lock:
                cached = self.detail_cache.get(str(album_id))
            if cached:
                details[str(album_id)] = cached
            else:
                missing.append(album_id)

        # 一次性批量补全缺失的详情（绝不能放进上面的循环里，否则 O(N^2) 重复请求）
        if missing:
            client = self._get_client()
            max_workers = min(16, len(missing))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(self._fetch_search_detail, client, album_id): album_id
                    for album_id in missing
                }
                # 整体超时保护：JM 抽风/限流时已完成的先采用，未完成的本次放弃
                done, not_done = concurrent.futures.wait(futures, timeout=25)
                for future in done:
                    album_id = futures[future]
                    try:
                        detail = future.result()
                    except Exception as e:
                        log.warning(f"处理搜索详情失败 {album_id}: {e}")
                        continue
                    if detail:
                        details[str(album_id)] = detail
                        with self._detail_cache_lock:
                            self.detail_cache[str(album_id)] = detail
                if not_done:
                    log.warning(f"搜索详情有 {len(not_done)} 个在超时内未完成，本次跳过（下次再补）")

            # 控制缓存体积（保留最近 3000 条）
            with self._detail_cache_lock:
                if len(self.detail_cache) > 3500:
                    self.detail_cache = dict(list(self.detail_cache.items())[-3000:])
            self._save_detail_cache_async()

        return details

    # ─── 搜索 ──────────────────────────────────────────────

    def _search_site(self, client, keyword: str, page: int, order_by: str,
                     time: str, category: str, sub_category):
        """兼容 jmcomic 新旧版本的站内搜索接口。"""
        search_kwargs = {
            "page": page,
            "order_by": order_by,
            "time": time,
            "category": category,
            "sub_category": sub_category,
        }
        if hasattr(client, "search_site"):
            return client.search_site(keyword, **search_kwargs)
        try:
            return client.search(keyword, **search_kwargs)
        except TypeError as e:
            if "main_tag" not in str(e):
                raise
            return client.search(keyword, page, 0, order_by, time, category, sub_category)

    def search_by_keyword(
        self, keyword: str, sort_order: str = "desc",
        page: int = 1, order_by: str = "mr", time_range: str = "a",
    ) -> List[Dict]:
        """关键词搜索，详情按需补充。

        order_by: mr=最新, mv=浏览量, mp=收藏量, tr=标题
        time_range: a=全部, t=今天, w=本周, m=本月
        """
        try:
            sort_order = (sort_order or "desc").strip().lower()
            if sort_order not in ("asc", "desc"):
                sort_order = "desc"
            page = max(1, int(page or 1))
            if order_by not in ("mr", "mv", "mp", "tr"):
                order_by = "mr"
            if time_range not in ("a", "t", "w", "m"):
                time_range = "a"

            # 搜索结果内存缓存：相同查询 / 翻回页直接返回
            cache_key = (keyword, sort_order, order_by, time_range, page)
            with self._search_cache_lock:
                entry = self._search_cache.get(cache_key)
                if entry and (time.time() - entry[0]) < self._search_cache_ttl:
                    log.info(f"搜索命中缓存: {keyword!r} p{page}")
                    return copy.deepcopy(entry[1])

            client = self._get_client()
            try:
                search_results = self._search_site(
                    client, keyword, page=page, order_by=order_by,
                    time=time_range, category="0", sub_category=None,
                )
                log.info(f"搜索成功，结果类型: {type(search_results)}")
            except Exception as e:
                log.warning(f"搜索失败: {e}")
                search_results = None

            if not search_results:
                return []

            try:
                if hasattr(search_results, "album_info_list"):
                    albums = getattr(search_results, "album_info_list", [])
                elif hasattr(search_results, "content"):
                    albums = list(getattr(search_results, "content", []))
                elif hasattr(search_results, "__iter__") and not isinstance(
                    search_results, (str, bytes)
                ):
                    albums = list(search_results)
                else:
                    albums = [search_results] if search_results else []
            except Exception as e:
                log.warning(f"获取专辑列表失败: {e}")
                albums = []

            if not albums:
                try:
                    tag_results = client.search_tag(keyword, page)
                    if (
                        tag_results
                        and hasattr(tag_results, "__iter__")
                        and not isinstance(tag_results, (str, bytes))
                    ):
                        albums = list(tag_results)
                except Exception as e:
                    log.warning(f"标签搜索失败: {e}")

            comics = []
            for album in albums:
                try:
                    comic_info = self._extract_search_result(album)
                    if comic_info:
                        aid = comic_info.get("id")
                        if aid:
                            # 封面 URL 纯本地构造（无网络），直接带上，前端可跳过逐个往返
                            try:
                                from jmcomic.jm_toolkit import JmcomicText
                                comic_info["cover"] = JmcomicText.get_album_cover_url(aid)
                            except Exception:
                                pass
                        comics.append(comic_info)
                except Exception as e:
                    log.warning(f"处理专辑信息失败: {e}, album: {album}")

            comics.sort(
                key=lambda x: self._parse_count(x.get("favorites", 0)),
                reverse=(sort_order == "desc"),
            )
            with self._search_cache_lock:
                self._search_cache[cache_key] = (time.time(), comics)
                if len(self._search_cache) > 200:
                    items = sorted(
                        self._search_cache.items(), key=lambda kv: kv[1][0], reverse=True
                    )
                    self._search_cache = dict(items[:150])
            return comics

        except Exception as e:
            log.warning(f"关键词搜索失败 '{keyword}': {str(e)}")
            import traceback
            traceback.print_exc()
            return []

    def _expand_single(self, tag: str) -> List[str]:
        """展开单个标签的全部同义词（含自身）。惰性导入避免循环依赖。"""
        try:
            from core.services.filter_service import expand_tags
            return expand_tags([tag])
        except Exception:
            return [tag]

    def search_by_tags(self, tags: List[str], max_total: int = 80, mode: str = "or",
                       input_tags: Optional[List[str]] = None):
        """多标签搜索。返回 (results_list, stats_dict)。

        mode='or'：包含任一标签；mode='and'：必须包含所有标签。
        input_tags：用户实际输入的标签（同义词展开前）。
        """
        if not tags:
            return [], {}
        tag_list = [str(t).strip() for t in tags if str(t).strip()]
        if not tag_list:
            return [], {}
        client = self._get_client()
        tag_counts = {tag: 0 for tag in tag_list}

        # 1) 并发抓取每个标签的前 2 页，收集候选 id（去重）
        candidate_ids = []
        seen_ids = set()
        tag_page_counts = {tag: 0 for tag in tag_list}

        def _fetch_tag_page(args):
            tag, page = args
            try:
                page_res = client.search_tag(tag, page)
            except Exception as e:
                log.warning(f"标签搜索失败 '{tag}' page={page}: {e}")
                return tag, []
            if not page_res:
                return tag, []
            ids = []
            for item in page_res:
                info = self._extract_search_result(item)
                if info and info.get("id"):
                    ids.append(info["id"])
            return tag, ids

        tasks = [(tag, page) for tag in tag_list for page in (1, 2)]
        max_workers = min(16, len(tasks)) if tasks else 1
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for tag, ids in executor.map(_fetch_tag_page, tasks):
                tag_page_counts[tag] += len(ids)
                for aid in ids:
                    if aid not in seen_ids:
                        seen_ids.add(aid)
                        candidate_ids.append(aid)

        tag_counts = tag_page_counts
        if not candidate_ids:
            tag_counts["_total"] = 0
            return [], tag_counts

        # 2) 批量补全详情（限制数量，避免过慢）
        pool_size = min(max_total * 2, 80)
        details = self.get_search_result_details(candidate_ids[:pool_size])

        # 3) 组装结果并过滤
        results = []
        for raw_id, detail in details.items():
            if not detail:
                continue
            detail_tags = {str(t).lower() for t in (detail.get("tags") or [])}
            if mode == "and":
                # 每个「原始输入标签」至少命中其任一展开同义词即算命中
                if input_tags:
                    hit = True
                    for ot in input_tags:
                        variants = {str(t).strip().lower() for t in self._expand_single(ot)}
                        if not (variants & detail_tags):
                            hit = False
                            break
                    if not hit:
                        continue
                else:
                    if not all(str(t).strip().lower() in detail_tags for t in tag_list):
                        continue
            results.append({
                "id": int(raw_id),
                "title": detail.get("title", "未知标题"),
                "author": detail.get("author", ""),
                "cover": "",
                "favorites": detail.get("favorites", 0),
                "tags": list(detail_tags),
                "_raw_tags": list(detail_tags),
                "pages": detail.get("pages", 0),
                "description": (detail.get("description") or "")[:100],
            })

        # 4) 排序并截断：命中用户实际输入名的作品优先
        if input_tags:
            lowered = {str(t).strip().lower() for t in input_tags if t}
            for r in results:
                raw = {str(t).strip().lower() for t in (r.pop("_raw_tags", []) or [])}
                r["_input_match"] = any(inp in raw for inp in lowered)
            results.sort(key=lambda x: (not x["_input_match"], -self._parse_count(x.get("favorites", 0))))
            for r in results:
                r.pop("_input_match", None)
        else:
            for r in results:
                r.pop("_raw_tags", None)
            results.sort(key=lambda x: self._parse_count(x.get("favorites", 0)), reverse=True)
        results = results[:max_total]
        tag_counts["_total"] = len(results)
        return results, tag_counts

    def search_by_author(self, author: str, max_total: int = 80) -> List[Dict]:
        """按作者搜索：站内关键词搜索后过滤作者字段（精确/包含匹配）。"""
        if not author or not author.strip():
            return []
        author = author.strip()
        try:
            candidates = self.search_by_keyword(author, page=1, order_by="mr", time_range="a")
            if not candidates:
                return []
            exact = [c for c in candidates if (c.get("author") or "").strip() == author]
            if exact:
                return exact[:max_total]
            fuzzy = [c for c in candidates if author in (c.get("author") or "")]
            return fuzzy[:max_total] or candidates[:max_total]
        except Exception as e:
            log.warning(f"作者搜索失败 '{author}': {e}")
            return []

    # ─── 下载 ──────────────────────────────────────────────
