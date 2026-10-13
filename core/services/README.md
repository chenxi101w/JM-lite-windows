# core/services/README.md

**职责**：JM 轻量版全部业务逻辑层（爬虫/下载/本地库/过滤/订阅/同步/回收站）；`core/app.py` 只做路由转发。

## 关键文件
| 文件 | 作用 |
|---|---|
| `jm_crawler/`（包） | JM 检索 + 下载引擎（并发/代理/进度钩子；改下载必看）。六个模块：`session` 下载会话与进度回调 · `option` 客户端与配置 · `cache` 封面与详情缓存 · `search` 搜索 · `download` 下载主链路 · `crawler` JMCrawler 组装与惰性单例；`__init__` 保持原对外名字 |
| `download_manager.py` | 下载任务编排与状态容器（进行中任务唯一真源） |
| `comic_manager.py` | 本地库：书架/收藏/分类/阅读进度/状态位 |
| `filter_service.py` | 关键词过滤与黑名单 |
| `subscription.py` | 订阅巡检（作者更新检查） |
| `sync_manager.py` | 云同步（自建服务器，多端进度） |
| `recycle.py` | 回收站（7 天可恢复） |

## 约定
- 本层不碰 Flask 请求对象；DB 访问统一走 `core/models/database.py`，不直连 SQLite。
- `jm_crawler` 为包：`JMCrawler` 由四个 Mixin（option/cache/search/download）组装，新方法按域放进对应 Mixin 文件，勿再堆回单文件；对外名字一律从包 `__init__` 走。

## 坑
- 并发只认 `download.threading.image/.photo`（`max_workers` 无效）；禁代理须传 `{'http':None,'https':None}`；`download_album(callback=)` 不是下载钩子，须子类化 `JmDownloader` 覆写。
