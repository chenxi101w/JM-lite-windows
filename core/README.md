# core/README.md

**职责**：JM 轻量版的后端根——只放装配与横切关注点，业务分别沉在 `web/`（HTTP 层）、`services/`（业务层）、`models/`（数据层）三个子包里。

## 关键文件
| 文件 | 作用 |
|---|---|
| `app.py` | **应用工厂** `create_app()`：装配 Flask → 初始化 DB → 注册蓝图 → 调度订阅巡检。对外仍暴露模块级 `app` 供 `desktop_app.py` 使用 |
| `config.py` | 路径与版本常量；`load_app_version()` 读项目根 `VERSION` |
| `logging_setup.py` | 全项目统一日志入口（`setup()` + `get_logger()`） |

## 约定
- **入口只有 `app.py`**：新增业务不要往这里塞，按域加进 `web/` 蓝图 + 对应 `services/`。
- **禁止裸 `print`**：一律 `get_logger()`（打包成 windowed exe 后 stdout 不可见）。
- 子系统细节见各自的 `README.md`。

## 坑
- `create_app()` 末尾必须**保留模块级 `app = create_app()`** —— `desktop_app.py` 依赖 `from core.app import app`，改成惰性获取会启动失败。
- `core/comics.db`、`core/jm_option.yml` 是**运行时自动生成**在 `core/` 下的，不可移动，靠 `.gitignore` 保护。
