# web/static/js/README.md

**职责**：前端业务脚本。按页面拆成 `window.JM` 命名空间模块；另有与 DOM 解耦的纯逻辑模块供 node 单测。

## 关键文件
| 文件 | 作用 |
|---|---|
| `core.js` | 命名空间根基：`JM.$`、`JM.api`（fetch 基元）、主题、Toast、PJAX 路由、`JM.pages` 注册表与 `routeInit()`、启动 |
| `ui.js` | 通用 UI 片段（卡片、骨架、空态、确认弹窗） |
| `search.js` / `downloads.js` / `library.js` / `settings.js` | 四个业务页的模块 |
| `reader.js` | 阅读器（连排/翻页/缩放/滑轨/览图）；**不参与 PJAX**，启动时单独初始化 |
| `reader-logic.js` / `library-drag-logic.js` | **纯逻辑**模块，不碰 DOM，可用 `tools/test_*.js` 直接单测 |

## 约定
- **无打包器，经典 script 顺序加载**：`base.html` 里的引用顺序**就是依赖顺序**（reader-logic → library-drag-logic → core → ui → search → downloads → reader → library → settings）。
- 每个业务模块形如 `(function (JM) { ... })(window.JM)`，顶部解构取用 `JM.$`、`JM.api` 等；`window.App === window.JM` 是兼容别名。
- 页面模块把 `init` 注册进 `JM.pages` 由 `routeInit()` 驱动；切页前用 `JM.regCleanup()` 登记的清理函数会先执行（防定时器叠加）。

## 坑
- **新增模块必须做三件事**：文件挂 `JM.*`、在 `base.html` 按依赖顺序引入、把 `init` 注册进 `JM.pages`。漏任何一步都会静默失效。
- 模块顶部**漏带前导**（如 `var cardHtml = JM.cardHtml` 写漏）只在运行时炸 —— 用 `tools/test_frontend_bundle.js` 真加载一次才能抓到。
- 改任何 js/css 后 `?v={{ app_version }}` 缓存键靠升版本刷新（见 `docs/ARCHITECTURE.md` §5 与准则 §3.3）。
