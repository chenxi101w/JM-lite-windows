# 📖 JMComicLite · JM 电脑版 lite

> **JM 漫画阅读器的轻量重写版** —— 只保留核心链路：**搜索 / 下载 / 阅读 / 书架（分类·收藏·黑名单·订阅巡检）**，
> 砍掉全部历史堆叠功能。启动更快、体积更小、界面更现代。
>
> 🆚 与[旧版 JMComicReader](https://github.com/chenxi101w/JMComicReader) 的取舍见下方[对比表](#-lite-vs-旧版)。

[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D4?logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/chenxi101w/JM-lite-windows?label=release&color=blue&cacheSeconds=60)](../../releases)
[![Downloads](https://img.shields.io/github/downloads/chenxi101w/JM-lite-windows/total?label=downloads&color=orange&cacheSeconds=60)](../../releases)
[![Tests](https://img.shields.io/badge/selftest-114%2B%20asserts-brightgreen)](tools/selftest_lite.py)

---

## 📸 预览（截图待补充）

> 将以下截图放入 `assets/screenshots/` 目录即可显示（文件名已对应）：
> `home.png`（主页·书架） · `search.png`（搜索） · `reader.png`（阅读器·连排/缩放） · `library.png`（分类树·回收站）

<p align="center">
  <!-- home.png 就位后取消下一行注释
  <img src="assets/screenshots/home.png" width="720" alt="主页·书架"/>
  -->
  <img src="assets/screenshots/search.png" width="720" alt="搜索"/>
  <!-- reader.png 就位后取消下一行注释
  <img src="assets/screenshots/reader.png" width="720" alt="阅读器"/>
  -->
  <!-- library.png 就位后取消下一行注释
  <img src="assets/screenshots/library.png" width="720" alt="分类树与回收站"/>
  -->
</p>

## ✨ 功能一览

| 模块 | 能力 |
|------|------|
| 🔍 **搜索** | 关键词 / 标签 / 作者 / JM 号，本地封面代理加速（多域轮换 + 成功域记忆），列数可调 |
| ⬇️ **下载** | 多线程高速下载（连接池复用），**断点续下**、取消秒响应、实时速度曲线、JSONL 下载日志 |
| 📖 **阅读** | 连排模式（多页一列 + 滚轮翻页 / 滑动翻页 / 缩放三模式）、右侧滑轨定位、览图一屏多页、Ctrl+滚轮缩放 |
| 📚 **书架** | 分类树（拖拽归类/调层级，含防环守卫）、收藏爱心、看完沉底、排序、每行列数、**回收站（7 天可恢复）** |
| 🔄 **订阅巡检** | 关注作者更新检查、云同步（多端进度同步，服务器自建） |
| 🎨 **界面** | 明暗主题跟随、Material 风格组件、原生窗口启动动画（秒弹）、便携免安装 |

<a id="-lite-vs-旧版"></a>
## 🆚 lite vs 旧版

| | **lite（本项目）** | [旧版 JMComicReader](https://github.com/chenxi101w/JMComicReader) |
|---|---|---|
| 定位 | 轻量 · 核心 | 功能全量（智能推荐 / 搜索偏好库等） |
| 启动 | ⚡ 秒级（原生预窗 + 端口优化） | 较慢 |
| 阅读 | 连排 / 翻页 / 缩放三模式 + 滑轨 + 览图 | 滚轮缩放 / 滚动 |
| 下载 | 连接池复用提速 4.3×，断点续下 | 真正限并发 |
| 书架 | 分类树拖拽 + 订阅巡检 + 回收站 | 基础书架 |

两条线并行维护：**要快、要干净用 lite；要全功能用旧版。**

## 🚀 快速开始

1. 到 [**Releases**](../../releases) 下载 `JMComicLite_vX.Y.Z_portable.zip`（约 28 MB）
2. 解压到任意目录，双击 `JMComicLite.exe`
3. 完了。数据全在 exe 同级 `UserData/` 文件夹里，换电脑整个文件夹拷走即可

> **运行要求**：Windows 10 / 11（64 位）+ Edge WebView2 运行时（Win11 自带，Win10 缺失时装一下）。无需 Python、无需装依赖。
>
> 想自己构建：`.venv-build\Scripts\python.exe build\_build.py` → 输出便携 zip 到 `dist_out\`

## 🧪 质量保障

```bat
tools\selftest_lite.py   :: 工程自检（114+ 项断言）
tools\smoke_test.py      :: 接口冒烟（40+ 项）
tools\verify_live.py     :: 实机端到端（启动→功能→重启持久化）
```

另有 reader / library-drag 两套纯逻辑模块的 node 单测（48 项），全部接入自检流水。

## 🧱 技术栈

Flask + pywebview(WebView2) + SQLite + Jinja2 + 原生 JS（零框架）· PyInstaller 打包
单页壳界面，主题走 CSS 变量（明暗跟随 / 手动切换）

## 📁 目录结构

```
desktop_app.py      启动链（UTF-8 / 端口 / Flask 线程 / pywebview / 浏览器兜底）
core/
  config.py         路径与版本
  app.py            全部路由
  models/database.py  建表与查询
  services/         爬虫 / 下载 / 本地库 / 过滤 / 订阅
web/                templates + static（js/css/图标）
build/              PyInstaller spec 与构建脚本
tools/              自检脚本（selftest / smoke / 实机验证 / 纯逻辑单测）
docs/               变更日志与发版铁律
```

## 🔗 相关项目

- [JMComicReader（旧版 · 功能全量）](https://github.com/chenxi101w/JMComicReader) —— 本项目的前身，功能更全但启动较慢

## ⚠️ 免责声明

- 本项目仅供**个人学习与技术研究**（Python 桌面打包 / 本地 Web 架构），不提供任何内容资源；
- 漫画内容均来自第三方公开站点，与本项目无关；请遵守当地法律法规，**未满 18 岁请勿使用**；
- 请勿将本项目用于任何商业用途。

## 📄 License

[MIT](LICENSE) © 2026 Chenxi
