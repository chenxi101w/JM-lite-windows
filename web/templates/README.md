# web/templates/README.md

**职责**：Jinja2 页面模板，一个页面对应一个文件；除 `base.html` 外全部继承它。

## 关键文件
| 文件 | 作用 |
|---|---|
| `base.html` | 页面骨架：侧栏 + 主区、主题初始化、**全部脚本与样式的引用**（含 `?v=` 缓存键） |
| `search.html` / `library.html` / `downloads.html` / `reader.html` / `settings.html` | 五个页面 |
| `subscriptions.html` | 订阅页片段 |

## 约定
- 页面只写**结构与占位容器**，渲染全靠 JS（模板里不塞业务逻辑）。
- 静态资源一律带 `?v={{ app_version }}`，改 CSS/JS 后靠升版本刷新缓存。
- 上下文由 `core/app.py` 的 `context_processor` 注入：`app_version`、`app_name`。

## 坑
- **脚本引用顺序在 `base.html` 里，顺序即依赖** —— 加新前端模块必须改这里，且位置要对（详见 `../static/js/README.md`）。
- 模板里的 `[hidden]` 需要显式 `display:none` 守卫：类选择器上的 `display:flex/grid` 会压过 UA 默认规则（`style.css` 末尾有统一守卫）。
- PJAX 会局部替换 `.main`，所以页面模板不要依赖整页重载的副作用。
