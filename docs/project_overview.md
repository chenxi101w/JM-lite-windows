# project_overview.md 项目总览
## 1. 基础信息
- 当前版本：2.14.0
- 运行平台：Windows 10 / 11（64 位，需 Edge WebView2 运行时）
- 项目核心定位与主要功能：JM 漫画阅读器的**轻量重写版**（JMComicLite），只保留核心链路——搜索 / 下载 / 阅读 / 书架（分类·收藏·黑名单·订阅巡检），砍掉旧版全部历史堆叠功能。便携免安装，数据全在 exe 同级 `UserData/`。

## 2. 技术与组件框架
- 编程语言、核心框架：Python 3.11+；Flask 3.1.3（本地 Web 服务）+ pywebview 6.2.1（WebView2 单页壳）+ SQLite；前端 Jinja2 + 原生 JS（零框架）
- 第三方依赖库/组件：jmcomic 2.7.8（检索/下载）、Pillow 12.3.0、requests 2.34.2；打包 PyInstaller 6.22.3
- 自研模块、内置工具组件：`core/web/` 蓝图路由层 + `core/services/` 七个业务服务；`web/static/js/` 七个命名空间业务模块（core/ui/search/downloads/reader/library/settings）+ 两个纯逻辑模块（reader-logic / library-drag-logic）；`tools/` 质量与隐私防护十件套

## 3. 迭代优化方向
### 3.1 性能&体验优化（不新增功能，优化现有逻辑）
1. 性能提速：启动链（原生预窗 + 端口探测用 bind）、封面多域轮换 + 成功域记忆、下载连接池复用（已提速 4.3×）
2. UI交互体验：阅读连排/翻页/缩放三模式 + 右侧滑轨 + 览图、书架分类树拖拽、卡片 UI、明暗主题跟随
3. 稳定性修复：下载断点续下、取消秒响应、假完成判定、端口占用兜底

### 3.2 新增体验功能（扩展项目能力）
- 功能描述：暂无（现阶段保持轻量定位，不做功能扩张）
- 实现思路简述：—
- 优先级：—

## 4. 项目边界【必填】
本项目**不打算实现**以下功能，用于限制开发范围：
- ❌ 不做在线智能推荐 / 搜索偏好库（旧版功能，lite 主动砍掉）
- ❌ 不做视频播放，仅支持本地漫画图片阅读
- ❌ 不做自动缓存（auto_cache 已明确不做）
- ❌ 不内置、不提供任何漫画内容资源，仅作为第三方公开站点的检索/下载/阅读客户端
- ❌ 不做账号体系；云同步为可选项，需用户自建服务器

## 5. 开发备注（可选）
- 构建：`.venv-build\Scripts\python.exe build\_build.py` → 便携 zip 输出到 `dist_out\`，并部署到 `D://Game//JMComicLite`（`UserData/` 保留）
- 构建环境 venv = **Python 3.11.9**（勿用 3.13，与全量版不同）
- 运行时数据目录 = exe 同级 `UserData\`，动态端口写在其中 `.app_url`；`core\comics.db`、`core\jm_option.yml` 由程序自动生成，靠 `.gitignore` 保护，不可移走
- 隐私防护：`private/` 目录放密钥（仅 `README.md` 入库）；提交前跑 `tools/privacy_scan.py`；换机需重跑 `tools/install_hooks.py` 安装 pre-commit
- 详见 `docs/已知坑与发版铁律.md`（踩坑）与 `docs/真机验证清单.md`（上线前检查）
