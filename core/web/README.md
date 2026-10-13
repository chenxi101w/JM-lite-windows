# core/web/README.md

**职责**：JM 轻量版的 HTTP 路由层——每个蓝图负责一个业务域的端点，只做「参数解析 → 调服务层 → 包统一响应」，不含业务逻辑。

## 关键文件
| 文件 | 作用 |
|---|---|
| `__init__.py` | `register_blueprints(app)`；函数内延迟 import 各蓝图，避免循环依赖 |
| `common.py` | 路由层公共设施：进程级单例（comic/download/sync manager）、统一响应 `ok()`/`fail()`、配置读取 `cfg()/cfg_int()/cfg_bool()`、设置写入白名单 `ALLOWED_SETTINGS` |
| `pages.py` | 7 个页面路由（返回 Jinja2 模板） |
| `system.py` | `/api/ping`、`/api/about`（存储明细扫描 + 60s 缓存）、`/api/settings`、`/api/sync/*` |
| `search.py` | 搜索：JM 号 / 关键词 / 标签 / 作者、详情补充、封面上游 URL、黑名单过滤与本地状态染色 |
| `downloads.py` | 下载：单本 / 批量 / 进度 / 取消 / 历史 / 历史删除；含 `_DownloadRegistry` 单例与全局线程池 |
| `reader.py` | 阅读：章节列表、整章页列表、单页图片、阅读进度落库、读完标记 |
| `library.py` | 书架：已下载列表、封面代理与书目录自愈、删除/回收站、收藏备份导入导出、分类 CRUD 与移动、黑名单 CRUD |
| `subscriptions.py` | 订阅：列表增删、巡检触发、新作记录与已读 |

## 约定
- 响应统一走 `common.ok()` / `common.fail()`，前端只判 `success`；**但 `/api/ping` 例外**，沿用旧契约 `{"ok": ...}`。
- 蓝图内需要的单例一律从 `core.web.common` 取（`comic_manager` / `download_manager` / `sync_manager`），不得各自 new。
- 新增可写入的配置键必须同步加进 `common.ALLOWED_SETTINGS`，否则被 `POST /api/settings` 静默丢弃。

## 坑
- `core/app.py` 只是**应用工厂**：`create_app()` 被调用后挂模块级 `app`，`desktop_app.py` 仍按 `from core.app import app` 使用，不要改成惰性获取。
- 封面负缓存键带 TTL（`_COVER_FAIL_TTL = 600`），新增封面端点务必复用 `_send_no_cover()` 兜底，否则 `img` 会破图。
- 下载进度状态机：`starting → preparing → downloading → processing → completed`；取消必须保留 TempCache（`_tempcache_file_count`）以支持续下。
