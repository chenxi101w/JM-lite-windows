# ARCHITECTURE.md 项目架构文档
## 1. 项目定位与技术栈
- 项目用途：JM 漫画桌面客户端（轻量版 JMComicLite）
- 运行平台：Windows 10 / 11（64 位）+ Edge WebView2
- 核心技术栈：Python 3.11 / Flask 3.1.3 / pywebview 6.2.1 / SQLite / Jinja2 / 原生 JS / PyInstaller 6.22.3
- 运行模式：客户端（本地 Flask 服务 + WebView2 套壳；WebView2 缺失时降级到系统浏览器）
- 性能目标：启动秒级；单进程常驻、长期后台无泄漏；下载走连接池；内存与体积优先（便携包约 28 MB）

## 2. 文件目录架构
```
project/test/
├─ desktop_app.py        启动链：UTF-8 设置 / 端口探测 / Flask 线程 / pywebview / 浏览器兜底
├─ VERSION               版本号（唯一真源，写完整三段 MAJOR.MINOR.PATCH）
├─ README.md             对外项目说明
├─ LICENSE / .gitignore / .gitattributes（统一 LF 换行）
├─ core/                 后端根（详见 core/README.md）
│  ├─ config.py          路径与版本常量
│  ├─ app.py             应用工厂 create_app()：装配 Flask、初始化 DB、注册蓝图（同时暴露模块级 app）
│  ├─ logging_setup.py   统一日志：RotatingFileHandler（2 MB × 2）替代裸 print
│  ├─ web/               路由层（蓝图包，详见 core/web/README.md）
│  ├─ models/database.py SQLite 建表与查询（唯一 DB 入口）
│  └─ services/          七个业务服务；jm_crawler 为同名包（session/option/cache/search/download/crawler，详见 core/services/README.md）
├─ web/
│  ├─ templates/         Jinja2 模板（详见 web/templates/README.md）
│  └─ static/
│     ├─ js/   业务脚本按页拆分为命名空间模块：core · ui · search · downloads · reader · library · settings；
│     │        另有与 DOM 解耦的纯逻辑模块 reader-logic.js · library-drag-logic.js（详见 web/static/js/README.md）
│     ├─ css/  style.css（主题用 CSS 变量）
│     └─ img/  app_icon.ico · no_cover.svg
├─ build/                JMComicLite.spec + _build.py + requirements.txt
├─ tools/                自检 / 冒烟 / 实机验证 / 纯逻辑单测 / 隐私防护（详见 tools/README.md）
├─ docs/                 项目说明书（本三件套 + 已知坑与发版铁律.md + 真机验证清单.md）
└─ private/              密钥归集目录（仅 README.md 入库）
```
> 复杂模块的局部细节见其目录下 `README.md`（`core/`、`core/services/`、`core/web/`、`web/templates/`、`web/static/js/`、`tools/`），本文件不重复描述。

## 3. 核心组件与依赖清单
- 第三方库/框架（附带版本号）：Flask 3.1.3、jmcomic 2.7.8、Pillow 12.3.0、pywebview 6.2.1、requests 2.34.2
- 系统/编译/打包工具依赖：Python 3.11.9（构建 venv `.venv-build`）、PyInstaller 6.22.3、Edge WebView2 运行时、Node.js（仅跑纯逻辑单测）
- 自研模块、工具类、公共函数：
  - `core/services/jm_crawler.py` —— JM 检索 + 下载引擎（并发/代理/进度钩子）
  - `core/services/download_manager.py` —— 下载任务编排与状态容器
  - `core/services/comic_manager.py` —— 本地库（书架/收藏/分类/状态位）
  - `core/services/filter_service.py` / `subscription.py` / `sync_manager.py` / `recycle.py` —— 过滤 / 订阅巡检 / 云同步 / 回收站
  - `core/web/common.py` —— 路由层公共设施：进程级单例、统一响应信封（`ok()` / `fail()`）、配置读取（`cfg()` 系列）
  - `core/web/*.py` —— 按域切分的蓝图：pages / system / search / downloads / reader / library / subscriptions
  - `core/logging_setup.py` —— 全项目统一日志入口（`setup()` 装配 + `get_logger(name)`）；**各层一律用它输出，禁止裸 `print`**（打包成 windowed exe 后 stdout 不可见，print 等于丢日志）
  - `web/static/js/core.js` —— 前端命名空间 `window.JM`：DOM 与 fetch 基元、主题、提示、PJAX 路由、启动
  - `web/static/js/reader-logic.js`、`library-drag-logic.js` —— 与 DOM 解耦的纯逻辑模块（可 node 单测）

## 4. 核心业务流程
- 程序启动初始化流程：双击 exe → `desktop_app.py` 设 UTF-8 → NativeSplash 原生预窗秒弹 → 探测可用端口（**用 bind，不用 connect_ex**）→ 起 Flask 线程 → `import webview` + WebView2 init → 内嵌 splash → `load_url` 主界面；WebView2 不可用时用系统浏览器打开
- 配置与数据加载流程：`core/config.py` 定位 exe 同级 `UserData/` → 读 `.app_url`（动态端口）→ `core/models/database.py` 打开 `core/comics.db` 建表/迁移 → `core/jm_option.yml` 由 `_apply_proxy` 幂等迁移下载配置
- 业务执行/页面渲染/接口链路：前端 fetch `/api/*` → `core/web/*` 蓝图 → 调用 `core/services/*` → 读写 SQLite → 返回统一 JSON 信封；页面为 Jinja2 模板 + 原生 JS 渲染。下载链路：`download_manager` → `jm_crawler`（`JmDownloader` 子类覆写钩子）→ 进度经回调写入状态容器与 `UserData/logs/download_log.jsonl`
- 前端页面生命周期：侧栏点击 → `pjaxNav` 局部替换 `.main` → `JM.routeInit()` 驱动已注册页面模块的 `init()`（阅读器走整页跳转、不参与 PJAX）；切页前先执行上一页登记的清理函数（`regCleanup`），防止定时器叠加

## 5. 项目专属约束
- 端口**动态**：必须写/读 `UserData/.app_url`，禁止硬编码端口
- 端口探测**必须用 `bind`**：`connect_ex` 会被杀软拦截回环出站，每次 ~1s，拖慢启动
- jmcomic 下载并发只认 `download.threading.image` / `.photo`（默认 **16×4**）；`max_workers` 无效
- 禁代理必须显式传 `{'http':None,'https':None}`，否则回落到 jmcomic 内置的 `127.0.0.1:5788`
- WebView2 的 HTML5 拖拽半残：拖拽功能必须 `preventDefault` + 鼠标事件模拟
- 前端脚本必须是**经典脚本 + 顺序加载**（无打包器）：新页面模块须挂 `JM.*` 并在 `base.html` 中按依赖顺序引入，同时把 `init` 注册进 `JM.pages`
- **构建与部署**：`.venv-build\Scripts\python.exe build\_build.py` → 便携 zip 输出到 `dist_out\`，并部署到 `D://Game//JMComicLite`（`UserData/` 原样保留，`appdata/`、`web/` 重建清残留）。
- 构建环境 = `.venv-build`（Python 3.11.9，依赖见 `build/requirements.txt`；**pywebview 6.x 必须显式装 `bottle` + `pythonnet`，否则打包后窗口起不来**）。
- 文本文件一律 **LF**（`.gitattributes` 锁定）：批量改写脚本必须显式 `newline="\n"`，否则产生整文件 diff
- 禁止裸 `print`：统一走 `core/logging_setup.get_logger()`；静默 `except: pass` 仅限**确属 best-effort 的清理/探测**（如临时目录删除、文件头嗅探），不得用于掩盖主流程失败
- 打包后 `core/comics.db`、`core/jm_option.yml` 自动生成于 `core/`，不可移动，靠 `.gitignore` 保护
