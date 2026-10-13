# -*- coding: utf-8 -*-
"""JMCrawler 组装（自 jm_crawler.py 拆出）。

四个 Mixin 的组装 + 惰性单例。"""

import os
import threading
from core.config import BASE_DIR, OPTION_FILE, TEMP_CACHE_DIR

from .option import OptionMixin
from .cache import CacheMixin
from .search import SearchMixin
from .download import DownloadMixin

from core.logging_setup import get_logger

log = get_logger("jm_crawler")

class JMCrawler(OptionMixin, CacheMixin, SearchMixin, DownloadMixin):
    """JM 漫画爬虫服务。"""
    def __init__(self):
        self.base_dir = BASE_DIR
        self.temp_cache = TEMP_CACHE_DIR
        self.option_file = OPTION_FILE

        os.makedirs(self.temp_cache, exist_ok=True)
        self._ensure_option_file()

        import jmcomic
        self.jm_option = jmcomic.JmOption.from_file(self.option_file)
        self.cover_cache_file = os.path.join(self.temp_cache, "cover_cache.json")
        self.cover_cache = self._load_cover_cache()
        self.detail_cache_file = os.path.join(self.temp_cache, "detail_cache.json")
        self.detail_cache = self._load_detail_cache()
        # 详情缓存异步落盘用的锁 / 状态标记，避免同步写大盘 JSON 卡住响应
        self._detail_save_lock = threading.Lock()
        self._detail_save_in_progress = False
        # 封面缓存异步落盘用的锁 / 状态标记（同详情缓存，避免每张封面全量同步写盘）
        self._cover_save_lock = threading.Lock()
        self._cover_save_in_progress = False
        # 内存详情缓存的读写锁，避免并发请求下字典迭代/重建竞争
        self._detail_cache_lock = threading.Lock()
        # 客户端复用：保留 HTTP keep-alive 连接池，重复搜索/翻页显著变快
        self._client = None
        self._client_sig = None
        self._client_lock = threading.Lock()
        self._cover_ok_prefix = None   # 上次成功的封面域前缀（域记忆，加速批量封面）
        # 搜索结果内存缓存：相同查询 / 翻回页即时返回
        self._search_cache = {}
        self._search_cache_lock = threading.Lock()
        self._search_cache_ttl = 120  # 秒

    # ─── jmcomic 选项与客户端 ───────────────────────────────

# ── 全局惰性单例 ──────────────────────────────────────────
# 进程内只保留一个 JMCrawler：构造时会同步加载 cover/detail 缓存等大 JSON，
# 放在 import 阶段会拖慢启动、窗口晚出现。改为首次使用时才构造。
_jm_crawler_instance = None
_jm_crawler_lock = threading.Lock()


def get_jm_crawler() -> "JMCrawler":
    """惰性单例：首次调用才构造 JMCrawler（提速应用启动）。"""
    global _jm_crawler_instance
    if _jm_crawler_instance is None:
        with _jm_crawler_lock:
            if _jm_crawler_instance is None:
                _jm_crawler_instance = JMCrawler()
    return _jm_crawler_instance
