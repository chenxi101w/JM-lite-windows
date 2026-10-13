# -*- coding: utf-8 -*-
"""JM 漫画爬虫服务（轻量版）。

从旧版搬改：保留搜索 / 详情 / 下载全部核心链路，含客户端复用（keep-alive）、
搜索结果内存缓存、详情缓存加锁与异步落盘、同义词展开接入（_expand_single）。

自 v2.15.0 起由单文件拆分为包：session（下载会话与进度）/ option（客户端与配置）/
cache（封面与详情缓存）/ search（搜索）/ download（下载）/ crawler（JMCrawler 组装）。
本 `__init__` 保持 `core.services.jm_crawler` 原有全部对外名字，引用方无需改动。
"""
from core.services.jm_crawler.session import (DownloadCancelled, _DownloadSession,
                                              _JmProgressCallback, _build_hooked_downloader)
from core.services.jm_crawler.crawler import JMCrawler, get_jm_crawler

__all__ = ["JMCrawler", "get_jm_crawler", "DownloadCancelled",
           "_DownloadSession", "_JmProgressCallback", "_build_hooked_downloader"]
