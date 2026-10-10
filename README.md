# JM 轻量版（JMComicLite）

JM 漫画阅读器的轻量重写版：只保留核心链路——**搜索 / 下载 / 阅读 / 书架**，
外加分类管理、黑名单、订阅巡检；其余历史堆叠功能全部砍掉。

- 技术栈：Flask + pywebview + SQLite + Jinja2 + 原生 JS
- 界面：单页壳（左侧栏 + 内容区），主题走 CSS 变量（明暗跟随/手动）
- 便携：exe 同级 `UserData/` 存放数据库、下载与缓存；更新程序只覆盖 exe + appdata

## 免责声明

- 本项目仅供**个人学习与技术研究**（Python 桌面打包 / 本地 Web 架构），不提供任何内容资源；
- 漫画内容均来自第三方公开站点，与本项目无关；请遵守当地法律法规，**未满 18 岁请勿使用**；
- 请勿将本项目用于任何商业用途。

## 运行（源码）

```bat
.venv-build\Scripts\python.exe desktop_app.py
```

## 自检与冒烟

```bat
.venv-build\Scripts\python.exe tools\selftest_lite.py   :: 工程自检（93+ 项）
.venv-build\Scripts\python.exe tools\smoke_test.py      :: 接口冒烟（40+ 项）
.venv-build\Scripts\python.exe tools\verify_live.py     :: 实机端到端（启动→功能→重启持久化，需已部署 exe）
```

## 构建（打包）

```bat
.venv-build\Scripts\python.exe build\_build.py
```

输出：

- `dist_out\JMComicLite_vX.Y.Z_portable.zip`（便携包，分享用）
- 自用解包版部署到 `D:\Game\JMComicLite`（可用环境变量 `JM_SELF_USE_DIR` 覆盖；
  部署只覆盖 exe 与 appdata，绝不碰目标目录的 UserData）

## 目录结构

```
desktop_app.py      启动链（UTF-8 / 端口 / Flask 线程 / pywebview / 浏览器兜底）
core/
  config.py         路径与版本
  app.py            全部路由
  models/database.py  建表与查询
  services/         爬虫 / 下载 / 本地库 / 过滤 / 订阅
web/                templates + static（js/css/图标）
build/              PyInstaller spec 与构建脚本
tools/              自检脚本
docs/               变更日志与发版铁律
```

## License

[MIT](LICENSE)