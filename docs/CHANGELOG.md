# 更新日志（CHANGELOG）

2026-10-13 2.14.0
移植准则试运行项目（project/test）的全部重构成果（行为等价移植，功能面不变：54 条 API 路由、7 个页面）
后端：core/app.py 1510 行拆为 43 行应用工厂 + core/web/ 蓝图包（8 文件）；新增 core/logging_setup.py 统一日志，全项目清除裸 print 78 处
下载引擎：core/services/jm_crawler.py（1310 行）拆为同名包（session/option/cache/search/download/crawler 六模块），对外名字不变
前端：web/static/js/app.js（2656 行）拆为 9 个命名空间模块，模板引用同步更新
工具：selftest_lite.py 升级至 114+ 项断言并内建 pyflakes 静态闸门；新增 test_frontend_bundle.js 前端模块束冒烟；smoke_test 云同步断言改为「默认不内嵌凭据」
文档：补齐 ARCHITECTURE.md 与 project_overview.md（三件套齐）；本条目起改用「日期 版本号」行格式（历史条目保留原样）
新增 .gitattributes 锁定 LF；版本号自本版起按三段 MAJOR.MINOR.PATCH 口径升位（重构 → MINOR）

## v2.13.10 — 2026-10-10

> **阅读页双进度条修复 + 收藏改爱心**。

### 双进度条
- 根因：连排模式靠原生滚动，`.reader__stage` 的原生滚动条与右侧主题滑轨同时可见
- 修复：连排模式隐藏原生滚动条（`scrollbar-width: none` + webkit），只留右侧滑轨（点按/拖动定位不受影响）

### 收藏爱心
- 收藏按钮 ★ → **爱心 SVG**；收藏态实心粉色 + popIn 弹跳（粉 `#f0537a` 系，与删除的红色系区分）
- 封面右上收藏角标 ★ → ♥，底色同步换粉

## v2.13.9 — 2026-10-10

> **书架删除/收藏 UI 美化**：按钮升级矢量图标 + 原生 `confirm` 弹窗换成自定义美化弹窗。

### 卡片按钮
- 收藏 ★ / 删除 🗑 的 emoji 字符 → 内联 **SVG 矢量图标**（与下载按钮同风格：线性描边、随主题变色）
- 收藏态：星形**实心填充** + popIn 弹跳动画；悬停上浮 + 图标放大；按下缩放回弹
- 删除按钮独立红色系悬停（`--danger`），与收藏行为区分

### 确认弹窗（confirmModal）
- 删除漫画 / 删除分类的原生 `confirm()` → 自定义弹窗：红色圆形图标徽章 + 标题 + 说明（含漫画名/「7 天内可恢复」高亮）+ 取消/删除按钮
- Promise 化（`await confirmModal({...})`），支持 ESC、点遮罩取消；**默认焦点在「取消」**（危险操作防手滑回车）；关闭带离场动画
- 复用现有 modal 遮罩 + `btn--danger` 体系，深浅主题自适应

## v2.13.8 — 2026-10-10

> **拖拽补丁 v2（真机修复）**：v2.13.7 实测仍拖不动且卡片右下出现僵死残影——根因修正：WebView2 的 HTML5 DnD 不是「不触发」，而是**半残**（dragstart 触发、原生拖拽接管、但 drop 永远收不到）。上一版「dragstart 出现就放弃模拟」方向反了。

### 修复
- **原生 DnD 一律 `preventDefault` 禁用**（grid/tree capture 阶段）：残影不再出现，WebView2 与真浏览器统一走鼠标模拟，双路不再打架
- 鼠标模拟全程接管：mousemove 在原生拖拽被取消后恢复正常，6px 阈值起拖 → 幽灵剪影 → 落点 handleDrop

### 重构
- 拖拽决策逻辑抽成**纯模块 `library-drag-logic.js`**（零 DOM）：`shouldBegin` / `resolvePayload` / `targetState` / `shouldDrop`，base.html 引入
- 新增 node 单测 `tools/test_library_drag_logic.js`（18 项全绿）接入 selftest（约 98+ 项）
- 拖拽中途窗口失焦（blur）清场，防残影残留

## v2.13.7 — 2026-10-10

> **修复书架拖动失效**：WebView2 的 HTML5 拖拽有已知 bug（WebView2Feedback#2805，dragstart 不触发），改用鼠标事件模拟拖拽兜底。

### 实现
- 拖拽落点逻辑抽成共用 `handleDrop(row, raw)`：HTML5 DnD 与鼠标模拟两条路共用一套归类/调层级代码
- 鼠标模拟（WebView2 补丁）：`mousedown` 起手（≥6px 阈值判定，普通点击不受影响）→ `mousemove` 移动幽灵剪影 + 高亮目标行（含 `drop-invalid` 防环守卫）→ `mouseup` 落点走 `handleDrop`
- 拖拽结束抑制紧随的 `click`（避免拖完误开阅读页/误选分类）
- 真浏览器中原生 DnD 正常时（dragstart 会触发）自动放弃鼠标模拟，双路不打架

## v2.13.6 — 2026-10-10

> 书架两处体验修复：**分类树支持拖拽调层级**（恢复旧版能力）+ **收藏不再整页闪烁**。

### 分类拖拽调层级
- 分类行 `draggable`：拖 A 分类落到 B 分类上 = 挂到 B 下；落到虚拟行（全部/收藏/未归类）= 移回顶层
- 防环守卫：不能落到自己或自己的子孙（`isDescendantCat`，UI 显示 `drop-invalid` 半透明禁用态）
- 协议：`text/plain` 分类=`cat:<id>`、漫画=纯数字，两种拖拽共存于同一棵树
- **后端修复**：`update_category` 的 `parent_id=0` 语义化为「顶层」→ 存 NULL（直接存 0 会撞外键约束，冒烟测试抓到）
- 后端冒烟：挂子级 / 移回顶层 / 重命名 ✓

### 收藏不闪
- 收藏/取消收藏改为**原地更新**：只切按钮态 + 增删 ★ 角标 + 重画左侧树（树无封面图，零闪烁）；不再全格重渲染
- 「收藏」视图里取消收藏 → 该卡片平滑移出列表

## v2.13.5 — 2026-10-10

> **阅读页连排模式（默认）**：整章多页纵向排一列，**滚轮滚动 = 翻页**（用户需求）。

### 实现
- `wheelMode='scroll'` 升级为连排：建列时每页 `loading="lazy"` + 预载宽高占位（`aspect-ratio`），滚动定位不漂移
- 当前页跟随视口（`ReaderLogic.columnIndex` 纯函数，node 单测 6 项）；进度落库 / 滑轨 / 览图 / 预读全联动
- 滚到底自动接下一章（防重入锁）；末章到底标记读完；Ctrl+滚轮 / 右键+滚轮 = 缩放（页宽 var(--pw)）
- 默认值 `zoom` → `scroll`，并一次性迁移老库中仍为 `zoom` 的行（显式选过 page 的不动）
- 设置页改名为「上下连排（滚轮滚动）」；`page`（滑动翻页）/`zoom`（以光标缩放）单页模式保留可切

### 验证
node 单测 36 项 ✓；selftest 全绿（~96+ 项）✓；/reader 与 /settings 路由冒烟 ✓；新库默认 scroll ✓

## v2.13.4 — 2026-10-10

> 清理：移除 v2.13.2 诊断埋点全链，代码回归生产形态；两项性能修复（bind 端口探测 + NativeSplash）原样保留。

### 移除
- `desktop_app.py`：`_START` / `_profile()` 及全部调用点、`run_desktop` 的 log 清空 + `JM_START_WALL` 注入
- `core/app.py`：`_log_first_serve()` / `_first_serve_logged` / 首页首服务计时
- 部署目录残留的 `UserData/startup_profile.log`（新版本不再生成）

### 顺手简化
- `configure_windows_app_id` 复用顶层 `ctypes` import（去局部重复 import）
- NativeSplash 注释去掉过时耗时数字；`_open_window` 并行注释同步精简

### 保留（性能修复不动）
- `_is_port_free` = **bind 探测**（杀软不拦本地 bind，端口检查 ~2s → ~0ms）
- NativeSplash 原生预启动窗

### 验证
py_compile ✓；selftest_lite 全绿（~96+ 项）✓；构建 v2.13.4 + 便携 zip（27.8 MB）并自部署 `D:\Game\JMComicLite`（UserData 原样保留）✓

## v2.13.3 — 2026-10-10

> **启动慢根因修复（端口探测 2.0s → ~0ms）**：`get_or_create_port` 的 `connect_ex` 回环探测被杀软（卡巴/火绒）逐次拦截 ~1s × 两个候选端口 = ~2s。改为 `bind` 探测——纯本地、零出站流量，杀软无感。

### 诊断过程（埋点说话）
v2.13.2 埋点实测：`after get_or_create_port` 独占 **2.033s**，其余全链仅 ~0.7s（import webview 0.03s / WebView2 init 0.54s / import core.app 0.05s）→ 瓶颈唯一且确定。

### 修复
新增 `_is_port_free(port)`：`socket.bind(("127.0.0.1", port))` 成功即空闲、失败即占用；`get_or_create_port` 改用之（保存端口 + 默认端口两候选，均不可用再随机兜底）。

### 教训（已入《已知坑与发版铁律》）
启动类慢务必**先埋点拿真实耗时**再下手，不要凭经验猜瓶颈——本次先后猜错 3 次（解压 / 原生窗 / Defender）。

## v2.13.2 — 2026-10-10

> 启动全链路埋点（诊断版）：`UserData/startup_profile.log` 逐阶段计时 + `JM_START_WALL` 对齐 app.py 首页首服务计时，实测出「双击到进入 ~2.7s」的真实分布。（v2.13.4 已移除）

## v2.13.1 — 2026-10-10

> **NativeSplash 原生预启动窗**（Win32 ctypes，零依赖）：在 `import webview` 之前弹出原生「正在启动…」窗，消除点开到 WebView2 splash 之间的纯黑屏期；任何异常静默降级，绝不阻塞主流程。体感「点了没反应」→「秒弹窗」（总时长不变，WebView2 桌面应用硬下限）。

## v2.13.0 — 2026-10-10

> **订阅页上线**：按作者分块聚合，组内按更新时间倒序，未读优先 / 已读沉底。

### 实现
- 新增 `/subscriptions` 页面 + `/api/subscriptions` 接口；DB 增 `get_read_book_ids`（已读集合批量查询）
- 前端三件套（subscriptions.html / base.html 导航 / app.js）同步落地

## v2.12.1 — 2026-10-10

> 动画策略定稿：**自适应**（无保底）——启动快一闪而过（**不为动画付一秒**），冷启动/慢时动画自然掩护。

### 定稿过程（用户洞察驱动）
- v2.12.0（无保底）→ 用户「没看到动画」→ 加 1.5s 保底 → 用户洞察「**没动画也只要 1s 就进去了**」→ 意识到保底 = 本末倒置（启动都快了，动画反成累赘）
- 最终：`_SPLASH_MIN_SECONDS = 0`（remain≤0 直接切换）——机制保留，未来如需保底改一个数即可

### 验证
mock 时长测试：快 boot → load_url ≈0s（直切）✓；慢 boot → 动画自然播满 ✓。

## v2.12.0 — 2026-10-10

> **启动加载动画（splash）**：双击后窗口立即出现、动画即时可见——把"干等黑屏"变成"立刻有反馈"。

### 实现（无缝单窗口，无外部依赖）
- `desktop_app` 重构启动编排：**窗口先于后端出现**——`webview.create_window(html=<内嵌 splash>)` 立即显示加载动画（脉冲 logo + 转圈 + 「正在启动…」，深浅色自适应）；
- 后端加载（含 `from core.app import app`）**后移**到 pywebview 的 GUI 就绪回调（`webview.start(func)`，独立线程）；
- 服务就绪后同窗口 `window.load_url(主界面)` **无缝切换**（无第二次窗口出现）；
- 启动预热线程（jmcomic/client）照常。

### 健壮性
- 三层回退完备：无 pywebview → 同步起服务 + 系统浏览器；后端启动失败 → 窗口显示错误提示页 + 写 `startup_error.log`；切换失败 → 记录日志不中断。
- `_boot_backend` 幂等（splash 切换与浏览器回退共用）。

### 验证
mock-webview 全流程编排测试：正常链路（splash 建窗 → boot → load_url 主界面 → destroy）✓、boot 失败切错误页 ✓、结构断言（幂等 + 重导入后置）✓；selftest 契约更新。

## v2.11.1 — 2026-10-10

> 启动提速：**import 链 1.10s → 0.48s（-56%）**（用户反馈「打开 app 有点慢」）。

### 诊断（逐层量化）
- `init_database` 5ms / `ensure_aliases_seeded` 22ms / DB 0.1MB —— 全部无关
- **大头是 import 链（1.10s）**：aiohttp 285ms（全项目只用于 1 个封面下载函数！）+ jmcomic 250ms + requests 121ms + flask 311ms（框架核心，不动）
- exe bootstrap / WebView2 冷启（不可控部分）另计

### 修复：重包惰性化 + 启动预热
1. **aiohttp 彻底移除**（-285ms + 打包剔除）：`download_manager._download_image_async` 改用 curl_cffi 同步请求（保持 async 签名，调用方零改动）。
2. **requests 惰性化**（-121ms）：`jm_crawler._download_cover` 改 curl_cffi；`sync_manager` 三处方法内按需 import。
3. **jmcomic 惰性化**（-250ms）：jm_crawler 9 处 / comic_manager 1 处使用点改函数内 import（钩子子类本就定义在工厂函数内，天然兼容）。
4. **启动预热线程**（desktop_app）：server 就绪后后台加载 jmcomic + 预构造 crawler/client（含域名更新）——**启动不阻塞，用户点搜索/下载时零等待**。

### 验证
import 链 1.10s → **0.48s** ✓；selftest 196 项 / smoke / 进度契约 / reader-logic / **真实下载** 全过 ✓；专项：两个封面下载函数真实拉图 124KB ✓、sync_manager 错误文案 ✓。

## v2.11.0 — 2026-10-10

> 技术栈组件升级（用户问「技术栈能升级吗」的实证答卷）：**下载引擎 jmcomic 2.6.20 → 2.7.8**，构建工具 PyInstaller 6.21.0 → 6.22.3。

### 版本盘点（对照 PyPI 最新）
| 组件 | 升级前 | 现在 | 状态 |
|---|---|---|---|
| Flask / pywebview / curl_cffi / Pillow / Werkzeug / Jinja2 | — | — | ✓ 均已是 PyPI 最新，无需动 |
| **jmcomic** | 2.6.20 | **2.7.8** | ↑ 本次升级 |
| **PyInstaller** | 6.21.0 | **6.22.3** | ↑ 本次升级 |
| Python | 3.11.9 | 3.11.9 | 暂不升（收益小、动静大）|

### jmcomic 2.7.8 兼容性预检（全绿）
- **API 14/14 通过**（JmModuleConfig/JmDownloader 六钩子/download_album/create_option_by_file/DOMAIN_IMAGE_LIST…）
- `decide_image_batch_count` 签名变化（2.7.8 需 photo 参数）**不影响本程序**：函数体仍是直接返回 `threading.image/photo`（并发语义不变）；产品代码从未直接调用。
- `_apply_proxy` / `_build_hooked_downloader` / `_clamp_concurrency` 均不受影响。
- 全量回归：selftest 196 项 ✓ / smoke ✓ / 进度契约 ✓ / reader-logic ✓ / **真实下载冒烟 ✓**（回调链/进度/日志全落账）。
- bench 速度对照：16×4 = **1.49 MB/s**（无回归，同水位）。

### 技术栈结论
「Flask + pywebview + SQLite」**不需要更换**——对本地桌面应用而言这仍是黄金组合（jmcomic 生态在 Python → 后端必须 Python；pywebview 依赖体积仅为 Electron 零头；SQLite 是本地数据的唯一理性选择），且组件层面已对齐最新。本次仅把**引擎与构建工具**升到最新。

## v2.10.0 — 2026-10-10

> 搜索列数（对齐手机端 `search_columns`，v6.0.20）——**「对齐手机端」差距清单至此收尾**。

### 搜索列数
- 设置 → 搜索 → 「每行列数」：自动（默认）/ 3 / 4 / 5 / 6。
- 搜索页进入时同步设置并应用（复用书架同一个元素级 CSS 变量 `--lib-cols`——按 grid 元素注入，书架/搜索互不干扰）。
- 与自动分页「加载更多」兼容（列数设在容器上）。

### 差距清单收尾说明（重要）
对齐手机端「JM 轻量版」的剩余差距全部处理完毕：
| 项 | 状态 |
|---|---|
| 书架排序 / 看完沉底 / 每行列数 | ✅ v2.8.0 |
| 收藏导入导出（跨端 JSON） | ✅ v2.9.0 |
| 搜索列数 | ✅ 本版 |
| auto_cache（智能缓存常看漫画） | ❌ **不做**——手机端自己在 v4.2.0「删除整条智能缓存链」（升级日志实锤），桌面无需对齐；现有「看完自动删除 + 回收站」机制更现代 |

### 验证
selftest 196 项 ✓ / smoke ✓。

## v2.9.0 — 2026-10-10

> 收藏备份（导出 / 导入）：对齐手机端「JM 轻量版」，**JSON 格式跨端互通**。

### 功能
- **导出**（设置 → 书架 → 收藏备份「导出收藏」）：全部收藏导出为 JSON 写到 `UserData/exports/jm_lite_favorites_日期_时间.json`（toast + 行内提示完整路径）。**零网络**：标题/作者从 detail_cache → 已下载表两级补全。
- **导入**（「导入收藏」选 JSON 文件）：解析 `favoriteBooks` 逐本写 BIT_FAVORITE；**已收藏幂等跳过**；返回「新增 N 本（备份共 M 本）」。
- **跨端兼容格式**（与手机端 `BookLibrary.exportFavorites` 完全一致）：
  ```json
  { "app": "jmcomicreader", "type": "favorites", "version": 1, "exportedAt": <ms>,
    "favoriteBooks": [ {"id": 123, "title": "", "author": "", "coverUrl": ""} ],
    "favTags": [] }
  ```
  - 手机端导出的备份可直接在本程序导入；本程序导出也可进手机端。
  - `favTags` 桌面轻量版无标签库（保留空数组占位）；导入时忽略额外字段。
- 后端：`get_favorite_ids()`（位查询）+ `GET/POST /api/favorites/export`（浏览器下载/写文件双形态）+ `POST /api/favorites/import`。

### 验证
全链路实测：导出三源补全（缓存/已下载表/裸 id）✓、导入跳过已收藏 ✓、幂等（二次 added=0）✓、脏数据拒绝 ✓；selftest 193 项 ✓ / smoke ✓。

## v2.8.0 — 2026-10-10

> 书架三项（对齐手机端「JM 轻量版」剩余差距）：**排序 / 每行列数 / 已读完沉底**。

### ① 书架排序（`shelf_sort`，设置已预留键复用）
- 书架工具栏右上角新增排序下拉：**最新下载**（默认）/ 最近阅读 / 标题 / 作者。
- 后端 `get_downloaded_comics(sort=...)` 加白名单排序映射（`SHELF_ORDERS`，防注入；非法值回落最新下载）：`download_desc` / `read_desc`（空阅读时间沉底）/ `title_asc` / `author_asc`。
- 切换即写设置并即时刷新（DB 持久，跨会话记忆）。
- 桌面适配说明：手机端的「阅读次数↓↑」「喜欢优先」依赖手机侧数据（read_count/标签引擎），桌面暂不做。

### ② 每行列数（`library_columns`，新增设置）
- 设置 → 书架 → 「每行列数」：自动（默认）/ 4 / 5 / 6 / 7 / 8。
- 注入 CSS 变量 `--lib-cols`（`repeat(var(--lib-cols, auto-fill), minmax(172px,1fr))`——未注入时回落自适应，搜索页/回收站不受影响）。

### ③ 已读完沉底（`library_finished`，对齐手机端 divider/hidden）
- 默认 **沉底 + 分隔线**（「已读完 · N 本」跨列分隔，未读完在前）；可选**隐藏**（书架不显示读完的）。
- 依赖已有 `finished` 字段（comic_status FINISHED 位），零新数据。

### 验证
四种排序 + 非法回落单测 ✓；API 端到端（设置保存 → 排序即时生效）✓；selftest 188 项 ✓ / smoke ✓。

## v2.7.3 — 2026-10-10

> 续修「有些封面没返回」（v2.7.2 代理后仍有漏网：拉取全失败时 404 破图）。

### 诊断（穷举排除）
- 封面缓存扫描：无坏文件（全真图 400×400~1065×1065）
- 真实本代理实测：**72 本 100% 成功**（中位 0.6s）；书架 3 本封面全绿
- 根因收敛：**特定网络环境下部分封面域全部不可达**时（服务端轮询 6~8 域全失败）→ 404 → img 破图；且失败单次要 **7.6 秒**（拖慢整页）

### 修复（三重兜底）
1. **占位图兜底**：拉取全失败时返回内置「暂无封面」SVG（**200**，`web/static/img/no_cover.svg`），前端 img 永不破图。
2. **失败负缓存**：失败的本 10 分钟内直接返回占位（`_cover_fail_until`）——页面刷新不再反复全轮询（实测第二击 **7.6s → 0.00s**）。
3. **书目录封面自愈**：封面拉取成功时顺手补书目录 `cover.jpg`（历史缺封面的已下载本自动修复）；`/api/cover/downloaded` 链路改为 书目录 → 缓存 → 实时拉取 → 占位，不再直接 404。
4. 前端 onerror 兜底统一：加载失败隐藏 img（不显示浏览器破图图标），搜索卡/书架卡两处。

### 验证
占位兜底 200 ✓ / 负缓存 0.00s ✓ / 真实本真图 ✓ / selftest 180 项 ✓。

## v2.7.2 — 2026-10-09

> 修复「**有些漫画封面没返回**」（用户截图：部分卡片破图）。

### 根因
搜索/详情页封面此前由 **WebView 直连远程 CDN**（img 标签走浏览器自己的网络栈，不经过下载链路配置的代理）。禁漫各 CDN 图片域常被网络环境干扰（部分域时通时不通）→ 部分封面破图。实测这些 URL 本身有效（直连 200）——问题在网络路径不在 URL。

### 修复：封面本地代理（服务端拉取 + 磁盘缓存）
- 新增 `GET /api/cover/proxy/<jm_id>`：服务端用配置好的 client（代理/session/headers）拉取 → **6 个图片域轮换重试**（`JmModuleConfig.DOMAIN_IMAGE_LIST`，单域 6s 超时）→ 落盘 `cover_{id}.jpg`（与回收站封面缓存同路径复用）。
- **成功域记忆**：拉通一次后记住该域，后续封面加载 0.35~0.9s（实测首拉 3.9s → 后续亚秒）。
- **格式嗅探**：CDN 按 UA 协商可能返回 webp（`.jpg` URL）——按文件头声明真实 MIME（jpeg/webp/png）。
- 前端三处切代理：搜索卡片 / 详情弹窗 / 回收站卡片兜底。
- 拉过一次永久缓存：URL 过期无碍，断网也能显示已缓存封面。

### 验证
实测 4 张封面全 200（jpeg/webp 混合）、缓存命中 0.002s、域记忆加速 ✓；selftest 175 项 ✓ / smoke ✓ / 进度契约 ✓。

## v2.7.1 — 2026-10-09

> 下载速度优化：**同环境基准实测提速 4.3 倍**（用户反馈「比手机端差远了」）。

### 根因与实测（tools/bench_download.py，同时间窗对照，同一本真实下载）
| 配置 | 时长 | 速度 | 相对 |
|---|---|---|---|
| 旧默认：curl_cffi 非session 8×2 | 58.8s | 0.16 MB/s | 1.0× |
| **新默认：curl_cffi_session 16×4** | **13.6s** | **0.70 MB/s** | **4.3×** |
| 试算：session 24×6 | 40.4s | 0.24 MB/s | 1.5×（并发过头回落） |

两轮独立基准方向一致（另一轮 0.50→0.86，1.72×；慢网窗口下旧配置受害更重）。

### 修复
1. **postman 换 session 模式**：jmcomic 默认 `curl_cffi`（非 session）= 每张图重新 TLS 握手（还带 chrome 指纹伪装的完整握手）；`curl_cffi_session` 复用连接池。慢网下省下的握手时间极为可观。
2. **并发 8×2 → 16×4**（基准最优组合；24×6 实测回落——不是越高越好）。
3. **老配置自动迁移**：`_ensure_option_file` 强制把 `client.postman.type` 写为 `curl_cffi_session`，并**主动提升** threading 至 16×4（此前 `_clamp_concurrency` 只封顶不提升，老配置的 8/2 不会升级——修复测试时抓到的第二个洞）。幂等。
4. 新增 `tools/bench_download.py`：未来调速直接跑基准（3 组对照免费复现）。

### 验证
迁移幂等 ✓；selftest 171 项 ✓ / smoke ✓ / 进度契约 ✓ / reader-logic ✓。

## v2.7.0 — 2026-10-09

> 三项用户需求：**下载续下**、下载卡片速度位置、搜索耗时显示。

### ① 下载续下（完整链路）
- **取消 = 保留可续**：`_cancel_download_cleanup` 不再清 TempCache、不再 delete_completely——取消/中断后已下部分全部保留，历史记「已取消（已下部分保留，可续下）」。想彻底清掉走书架删除。
- **空壳放行**：`api_download_comic` 对「DB 有记录但 DownloadedComics 无真实文件」的历史残渣（假完成时代产物）自动清壳放行——续下/重下同一本不再被「已下载」误拦。
- **续传提示**：`download_comic` 开始时报「续传：检测到已下 N 个文件，自动跳过已下部分...」；已下好的图由 jmcomic 的 skip 机制自动跳过，从断点继续。
- **历史列表「续下」按钮**：`/api/download/history` 新增 `resumable` 字段（未在库 + TempCache 有残留）；下载页历史区渲染「续下」按钮，一键从断点继续。
- 实测：预置残留文件 → 提示正确出现 → skip 正常 → 日志字节守恒。

### ② 下载卡片：速度挪到百分比左边
右侧行改为 `464 KB/s · 36%`（速度在百分比前）；左侧行只留 大小 · 已下/余章数。

### ③ 搜索耗时（筛选行右侧空白处）
「关键词/标签/作者/排序」一行右端显示「用时 X.XX s」（端到端计时：请求+响应），每次搜索后更新。

### 验证
selftest 169 项 ✓ / smoke ✓；续下链路功能实测（提示 + skip + 取消保留 + 空壳判定 helper）✓。

## v2.6.1 — 2026-10-09

> 修复：多章本（2 章一批下载）**进度回跳 / 长时间停滞**（用户实锤「一直 36%」，现场取证：下载火力全开但进度不动）。

### 根因
进度分母用的是**「已开始下载章节的页数」**。jmcomic 按 `threading.photo=2` **2 章一批**调度（批内并发、批间串行），每换一批分母突然跳大：
- 批末进度冲到高值（如 80%）→ 新批分母翻倍 → **回跳到 50%**；
- 批内每下 1 页 ≈ 涨 0.1~0.3% → 长章节本看起来「卡住」；
- 99 章本（用户案例 454204）尤其严重。

### 修复：批间连续公式
`frac = (已完成章数 + 进行中章的页数完成比) / 总章数`

推导（关键不变量）：章完成瞬间 `done+1` 且该章移出「进行中」批 → `(done+1)/total ≡ (done + 该章页/该章页)/total`，**恒等连续**。由此在**全本总页数不可得**（禁漫 `page_count` 对多章本恒为 0，已实测 454204/1252411）的情况下，仍做到：
- 分母 = 总章数（`len(album)`，全程恒定）→ **换批零回跳**；
- 分子含章内页数比 → **章内持续走动**；
- 已下页/总章数实现为 `done_pages` 记账（after_photo 累加），负值 clamp 防图片失败场景。

### 顺带
- `before_album` 总章数改 `len(album)`（`JmAlbumDetail.__len__`=episode_list 长度，零网络；jmcomic **没有** `photo_count` 属性，旧代码 `len(list(album))` 白构造 N 个对象）。
- 新增 **`tools/test_progress_model.py`**：直驱进度回调的契约测试（零网络零 fake 依赖），锁死不变量：全程单调 / 首 20 末 80 / 批界不回跳 / 99 章场景 / 全 skip 重下照常推进 / before_image 可即时取消；接入 selftest。

### 验证
selftest 161 项 ✓ / smoke ✓ / 真实下载冒烟 ✓（真实单章本 20→80 全程递增）。打桩过程发现问题：fake 需完整过 jmcomic 钩子链（dunder 必须定义在类上）——已改为直驱 cb 的零依赖测试法。

## v2.6.0 — 2026-10-09

> **代码重构**（无新功能、行为不变）：清死代码、抽下载会话与状态注册表、阅读器纯逻辑分离并配真实单测、CSS 归位、注释瘦身。

### 块① 死代码清理
- 删 `_watch_speed()` 存根（重构后 14 行死代码）、`DownloadCallback` 无用导入。
- **`cancelling` 中间状态全链路移除**（取消早已改「立即置 cancelled」，该状态永不出现）：后端判断、前端 class/文案/变量共 5 处，及 `.dl-item--cancel`/`.dl-item__spin` 两条死样式。

### 块② 下载子系统收拢
- **`_DownloadSession`**（jm_crawler）：吸收「每秒速度采样线程 + 三结局日志落盘」，`download_comic` 只管下载；**102 → 83 行**，finally 一行 `session.finish()`。
- **`_DownloadRegistry`**（app.py）：`_dl_lock`/`_dl_progress`/`_dl_cancel_events` + 5 个散落函数 → **1 个内聚单例**，方法化（register/update/is_downloading/cancel/snapshot/get/discard/remove），端点引用全部改走 `_registry`，并补状态机文档（starting→preparing→downloading→processing→终态）。
- 全链路实测：登记/轮询/透传/取消立即生效/移除 5 步断言通过。

### 块③ 阅读器拆分 + 真实单测（样板）
- 新增 **`web/static/js/reader-logic.js`**：抽出三块今天被反复修改的纯逻辑——`resolveWheelAction`（滚轮判定：右键缩放/滑动翻页/页内滑动/冷却）、`railIndex`（滑轨 Y→页索引）、`buildOverviewHtml`（览图网格）。无 DOM 依赖。
- app.js 改为调用模块（滚轮 handler 从 30 行内联逻辑瘦身为编排）；`base.html` 按序加载。
- **新增 `tools/test_reader_logic.js`：node 真跑 24 项单测**（滚轮 12 项边界 + 滑轨 7 项 + 览图 5 项），并接入 selftest —— 对治「打桩绿≠生效」的系统性教训，从符号存在性检查升级为行为断言。

### 块④ 整洁度
- **CSS 归位**：今天追加的三段样式（关于页存储明细/滑轨+览图/色板）从文件尾部移入对应分区，修掉 `.about-line` 与 `.storage-list` 粘行的格式事故；`.reader` 的 `position: relative` 合并进主规则。
- **注释瘦身**：`_apply_proxy`/`_build_hooked_downloader`/`_JmProgressCallback` 等超长「踩坑叙事」压成结论 + 硬约束（过程细节在 CHANGELOG）。
- **selftest 精简**：下载契约 30 条琐碎断言合并为 13 条高密度契约；修正 3 处因重构失效/写错的断言（含 `head -12` 截断曾掩盖的 NameError 崩溃——现有测试首次完整跑完）；CSS 变量检查支持运行时注入变量白名单（`--rail-color`/`--cols`/`--sw`）。

### 验证（六项严格判定，全部用退出码）
Python 编译 ✓ / JS 语法 ✓ / selftest **156 项** ✓ / smoke ✓ / 真实下载冒烟（回调链+采样落账）✓ / reader-logic 单测 **24 项** ✓。

## v2.5.0 — 2026-10-09

> 复刻手机端两项阅读器能力：**右侧进度滑轨**（`reader_progress_color`）+ **缩略图览**（`reader_pages_per_screen`）。

### 右侧进度滑轨（对齐手机端 ReaderProgressRail）
- 阅读器右侧 6px 细竖条（hover 变 9px），顶部→底部按当前页填充。
- **按下即定位、拖动实时预览、松开跳页**：拖动时只更新填充与页码（不请求），松开才 `renderPage`——避免拖动经过多页时狂发图片请求。
- 颜色来自设置 `reader_progress_color`（默认 `#7B6FE0`），设置页提供 6 个预设色 + 自定义取色器。
- 览图模式下自动隐藏滑轨。

### 缩略图览（对齐手机端「缩略图览」）
- 顶栏新增「览图」按钮（览图 ⇄ 回到阅读）。
- 网格显示当前章全部页面缩略图（`loading="lazy"`），**点击任意页直接定位阅读**；当前页高亮描边（颜色同滑轨）、自动滚入视野。
- 列数来自设置 `reader_pages_per_screen`（1~6，默认 1）：1 = 自适应列宽，2~6 = 固定列数。
- 览图模式下翻页/换章只更新高亮与页码，**不加载大图**（省流量）；`↑↓` 滚动网格；`Esc` 先退出览图再退出阅读器。

### 其他
- 阅读器底部提示文案更正（滚轮已默认滑动翻页、右键+滚轮缩放、拖动滑轨定位、览图一屏多页）。
- 设置页新增「览图列数」「进度滑轨颜色」两行；两键加入写入白名单。
- 新增 `[hidden]` 守卫样式（作者样式会覆盖 hidden 属性，览图/滑轨切换必须显式 `display:none`）。
- selftest 加 10 条契约断言；后端实测：阅读器/设置页模板渲染 + 两个新设置键读写 + smoke 全绿。

## v2.4.1 — 2026-10-09

> 进行中卡片信息精简（用户要求）：只留 **下载大小 · 速度 · 已下/余章数**。

### 问题
卡片把后端消息与前端行拼接，导致重复啰嗦：
`下载 7/43 章 · 已下 202/207 页 · 7/43 章 · 192 图 · 96.7 MB · 464 KB/s`
（「7/43 章」出现两次，页数/图数冗余。）

### 修改
- 下载中（`downloading` 且已有数据）**只显示精简三项**：`96.7 MB · 464 KB/s · 已下 7 章 · 余 36 章`。
- 章数改为「已下 N 章 · 余 M 章」（已下载/未下载，用户口径）。
- 不再展示页数、图数；不再拼后端消息。
- 其余阶段（准备中/整理中/取消/失败）保留状态文案（如「正在获取漫画信息...」），避免无数据时空白。
- 无总章数时退化为「已下 N 图」。

### 验证
selftest 加 2 条契约断言、smoke 全绿；真实下载冒烟照跑 PASS（回调链未受影响）。

## v2.4.0 — 2026-10-09

> **下载子系统史上最大修复**：进度回调从未生效的真相 + 假 completed + 并发计数竞争 + 系统代理跟随。

### 根因（下载日志 5 条全零回调实锤）
`jmcomic.download_album(album_id, option, callback=...)` 的 **`callback` 参数根本不是下载钩子**——它只是「下载完成后拿 album/downloader 的返回值回调」（api.py: `callback(album, dler)`，在整个下载结束后调用一次）。此前把 `_JmProgressCallback` 传给它：下载结束后被当函数调用 → `TypeError` → 进 fallback 重下。**进度回调从项目诞生起就没工作过**：
- 日志 5 条记录（4 条 completed）全部 `chapters=0 pages=0 imgs=0 bytes=0`——回调一次没触发；
- 4 条「completed」是**假 completed**：jmcomic 先建 Pid 子目录，图片全失败时 `os.listdir` 也能看到子目录名 → 误判成功；
- 用户看到的「0 / 5 / 36%」是固定阶段点 + fallback 的 40/60/80 混乱组合，且 photo=2 并发下共享的 `_chapter_imgs/_chapter_pages` 会被并发章的 `before_photo` 互相清零（进度乱跳的另一来源）。

### 修复
1. **回调注册正道**：新增 `_build_hooked_downloader(cb)` —— 子类化 `JmDownloader` 覆写 6 个钩子（before_album/photo/image、after_image/photo/album），转发给进度收集器并调 `super()` 保留 jmcomic 自身机制；`download_album(downloader=...)` 传类，`_simple_download` 同样挂钩。
2. **进度模型去竞争**：弃用共享章状态，改**全局计数**（锁保护）：`pct = 20 + min(1, imgs_done/pages_total) × 60`——imgs_done 只增不减，pct 天然单调；消息改 `下载 x/y 章 · 已下 i/N 页`。
3. **假 completed 修复**：completed 判定改 `os.walk` 只数真实文件，零文件明确报「下载失败：未产出任何图片文件」。
4. **系统代理自动跟随**：proxy_enabled=0 时探测 Windows 系统代理（winreg IE 设置），有则自动用作下载代理（直连被墙时梯子自动生效），无则显式直连——还原 jmcomic「use system proxy」的本意但用真实探测值，永不回落 127.0.0.1:5788。

### 验证（真实下载，非打桩）
沙箱直连实测 jm=1480569：**26 图 / 9.53MB / 13.5s 下载成功**，回调链首次真正落账（chapters=1、pages=26、imgs=26、size_mb=9.53），进度 `20% 已下 0/26 页 → 22% → … → 80% 已下 26/26 页 → 80% 下载 1/1 章` 单调实时；8 线程池（image=8）精确生效；meta_data 实测 `timeout=30`、proxies 直连无 5788。selftest 契约全面更新、smoke 全绿。

## v2.3.0 — 2026-10-09

> **网络层重大修复**：「重下还是 0 KB/s + 取消一直取消中」的真正根因——jmcomic 默认代理劫持。

### 根因（实锤）
jmcomic 的 `JmModuleConfig` 在 option 未配置 proxies 时会注入
`DEFAULT_PROXIES = 127.0.0.1:5788`（注释「use system proxy by default」，实为硬编码）。
我们的 `jm_option.yml` 没有 proxies 字段 → **所有请求都往本机 5788 端口打**：
- 代理软件不在这个端口 → 全部连接失败 → **零字节（0 KB/s）**；
- 卡在 `get_album_detail`/`get_photo_detail` 阶段（进度 30%「正在获取漫画信息...」）；
- detail 阶段**没有任何取消检查点** → 点取消后长时间「取消中」；
- 最终 jmcomic 收集失败不抛（`check_exception=False`）→ 记成 failed「下载未完成」而非 cancelled。
之前能成功下载的 2 本，应是当时 5788 端口恰好有代理在跑。

### 修复
1. **代理显式接管**：`_apply_proxy` 重写——代理开 → 用户配置的代理；**代理关 → 显式直连** `{'http': None, 'https': None}`（requests 官方禁代理语义，同时屏蔽环境变量代理；注意 `proxies=None` 会被 postman 的 merge_kwargs 跳过、漏回 jmcomic 默认值，必须用「值为 None 的键」）。
2. **HTTP 超时**：`meta_data['timeout'] = 30s`（postman 的 meta_data 会 merge 进每个请求 kwargs，requests/curl_cffi 都吃）。根治「无超时死连接挂死」——即使域名被墙也会在 30s 内失败重试而非永久卡住。
3. **`before_image` 取消检查点**：jmcomic 在 skip 判断**之前**调用该钩子，此前 callback 没实现它——重下时 TempCache 残留文件被大批 skip，整段零回调零检查点。现在 skip 图也推进度（`_chapter_imgs` 计数）+ 可即时取消；已存在文件字节单独计入 `_skip_bytes`（日志 `size_mb` = 新下载 + 已存在，「这本多大」才准确）。
4. **取消立即生效**：cancel 接口直接置 `cancelled`（前端马上变已取消态、3s 后移出列表、可立即重下同本），TempCache/本地内容清理由下载线程真正退出时收尾（对已移除记录 no-op，无幽灵复活、历史不重复）。

### 验证
- e2e：代理关/开两种注入值实测正确；skip 场景日志 pages=3/imgs=1/size_mb=1.48（0.5 已存在 + 1.0 新下载）守恒；before_image 检查点即时抛 `DownloadCancelled` 且日志 status=cancelled。
- selftest 加 5 条契约（显式直连/超时注入/before_image/skip 字节/取消立即生效）、smoke 全绿。

## v2.2.3 — 2026-10-09

> 修复：整章下载期间进度冻结 / 消息停留「正在获取漫画信息...」/ 速度 0 KB/s（用户截图实锤）。

### 根因
v2.1.1 把字节累计挪到 `after_image` 后，**`after_image` 只累加字节、不回调进度**——`_dl_progress` 的 `bytes` 只在 `after_photo`（整章完成）时更新。于是一章下载几十秒期间：进度条冻结在上一个整数点、消息停留在阶段文案、前端按字节增量算的速度恒为 0。

### 修复：逐图推进度（章内插值）
- `before_photo` 记录本章页数 `_chapter_pages`（同时清零 `_chapter_imgs`）。
- `after_image` 每张图落盘后立即调 `_emit_image_progress()`：
  - **百分比章内插值**：`20 + (已完成章 + 本章完成比) / 总章数 × 60`，进度条平滑走动而非整章跳变；
  - **实时消息**：`下载章节 3/12 · 本章 17/24 页`；
  - `bytes/images` 随 extra 实时透传 → 前端速度（字节增量 + EMA）每 1.5s 轮询都能算出真值。
- `after_photo` 边界上报保留。每图一次 dict 更新（锁内），开销可忽略。
- 打桩端到端验证：8 图 2 章，pct 单调递增、章内递增、跨章 `done` 正确、字节实时；selftest 新增 3 条契约断言。

## v2.2.2 — 2026-10-09

> 「关于」页存储占用细化：每个额外存储位置逐项列出 + 程序本体（非额外占用）单列，带占比条。

### 存储占用明细
- `/api/about` 新增 `storage_items`：**一次 `os.walk` 遍历安装根**归桶（0.2s 级），**60s 缓存**避免反复全盘扫描。结果守恒：程序本体 + 用户数据 = 总计。
- **额外存储逐项固定列出**（空目录也显示 0 B）：
  - 已下载漫画（`UserData/DownloadedComics`）
  - 临时缓存——封面/详情缓存 + 下载中转（`UserData/TempCache`）
  - 数据库与配置——comics.db / jm_option.yml（`UserData/core`）
  - 下载日志——download_log.jsonl（`UserData/logs`）
  - 阅读器内核数据（`UserData/webview_data`）
  - 其他用户数据（未归类部分，0 时隐藏）
- **非额外占用 = 程序本体**（exe / 依赖 / 内置资源，即安装根除 UserData 外的一切）单独一行。
- 关于页 UI：每行 = 名称 + 大小 + 占总计百分比 + 占比条 + 相对路径；顶部总计行显示「总计 X（程序本体 Y + 用户数据 Z）」。
- 部署态实测：总计 202.0 MB = 程序本体 54.1 + 用户数据 147.9（webview_data 146.2 占大头）。selftest 新增 `test_about_storage()` 9 条断言。

## v2.2.1 — 2026-10-09

> 新增极简下载日志（JSONL，一行一本），攒数据用于分析服务器下载速度惯性；顺带修复取消链路被吞的 bug。

### 下载日志 `UserData/logs/download_log.jsonl`
- **一行一本、追加写**，字段刻意精简，正对「惯性分析」需求：
  ```json
  {"jm_id":123,"ts":"2026-10-09 14:00:00","status":"completed","duration_s":85.3,
   "chapters":12,"pages":240,"imgs":240,"size_mb":50.0,"avg_mb_s":0.59,"samples_mb":[0.0,1.2,...]}
  ```
  - `samples_mb`：**每秒下载的 MB**（即瞬时 MB/s，纯内存读 `after_image` 字节计数器，零 IO 开销）
  - `duration_s` 下载了几秒；`chapters` 章节数；`pages` 全本总页数（`before_photo` 逐章累加 `len(photo)`）；`imgs` 实际下载图数（取消/失败时小于 pages）；`size_mb` 大小；`avg_mb_s` 平均速度
  - `status`：completed / cancelled / failed，三种结局都落日志
- 写入线程安全（模块锁）、失败静默（绝不影响下载本体）；约 5KB/本，无轮转（千本 ≈ 5MB）。

### 顺带修复：取消被记成 failed
- `jm_crawler.download_comic` 外层 `except Exception` 会兜住 `DownloadCancelled`，导致取消向上传不到 `_cancel_download_cleanup`——取消后被记成「失败」，TempCache 也不清理。补 `except DownloadCancelled: status="cancelled"; raise`，与 `download_manager` 三层的 re-raise 接力成完整链路。日志状态因此能正确区分 `cancelled`。
- 端到端打桩验证三路径（completed/cancelled/failed）字段与状态全部正确；selftest 新增 4 条日志契约断言。

## v2.2.0 — 2026-10-09

> 阅读器滚轮交互重做：滚轮上下滑 = 滑动翻页；按住右键 + 滚轮 = 以光标为中心缩放。

### 滑动翻页（新默认）
- 滚轮行为新增 **page（滑动翻页）并设为默认**：宽度铺满一页，页高超出视口时滚轮先在页内滑动（每次约 85% 视口高），**到底/到顶自动翻下一页/上一页**（跨章节衔接）。
- 累计 `deltaY` 阈值（40）+ 240ms 冷却：防触控板小步连续触发导致连翻。
- 设置页「滚轮行为」改为三选：**滑动翻页（默认）/ 以光标为中心缩放 / 上下滚动**，选项下附「右键+滚轮=缩放」提示；设置摘要 `WHEEL_NAMES` 同步。

### 右键缩放
- **任何滚轮模式下**，按住右键 + 滚轮 = 以光标为中心缩放（`e.buttons & 2` 判定，不依赖设置）。
- 阅读器舞台屏蔽系统右键菜单（`contextmenu` preventDefault），右键只服务缩放手势。

### 其他
- 原有「上下滚动 / 以光标缩放」两种模式行为不变；部署端已存的 `reader_wheel_mode=scroll` 已按用户要求改为 `page`。
- selftest 新增滚轮契约断言：默认 page、右键缩放判定、右键菜单屏蔽、累计阈值、设置页含「滑动翻页」选项。

## v2.1.1 — 2026-10-09

> **下载链路重大修复**：重复下载 / 进度不动 / 速度掉 0 KB/s。根因是并发配置写错了键，导致 480 线程爆炸。

### 根因（实测取证，非推测）
用 `jmcomic.create_option_by_file()` 实测部署目录的 `jm_option.yml` 后确认：
- **`max_workers` 是幽灵键**：`download.threading` 是宽松 `AdvancedDict`，未知键静默忽略，jmcomic **从不读取** `max_workers`。v2.1.0 把它从 5 调到 12 属于**无效改动**（并发一点没变），此处更正。
- **`batch_count` 是旧版别名**：`compatible_with_old_versions()` 会把它改写成 `threading.image`。真正生效的键只有 `threading.image`（单章内图片并发）和 `threading.photo`（同时下载章节数）。
- 部署配置实测 `image=30`、**`photo=16`（jmcomic 默认值，我们从未配置过）**。
- 而 `execute_on_condition()` 在 `batch >= 对象数` 时走 `multi_thread_launcher`——**每个对象一个线程、完全不设上限**。
- 于是实际并发 = 16 章 × 30 图 = **最多 480 个线程**，每个还带 `image.decode: True` 的 Pillow 解码 → 8 核 CPU/GIL/磁盘全面过载 → **进度卡住、字节写入断续、速度采样读不到**，三个症状同源。重复下载则是「看着卡住又点一次」+ TempCache 搬走后 jmcomic 的 exists-skip 永不命中。

### 修复
- **并发改用真实键并封顶**：`DOWNLOAD_IMAGE_CONCURRENCY=8`、`DOWNLOAD_PHOTO_CONCURRENCY=2`（8×2=16 并发）。新增 `_clamp_concurrency()` 做 `[1, ceiling]` 封顶——这里刻意封顶而非保底，因为超限会退化成每对象一线程反而更慢。
- **迁移老配置**：`_ensure_option_file` 现在 `pop` 掉 `batch_count`（会覆盖我们的设置）与 `max_workers`（纯误导），并写入真实的 `image`/`photo`。实测旧配置迁移后 `image=8 photo=2`。
- **速度/进度改用真实字节**：新增 `_JmProgressCallback.after_image(image, img_save_path)`，在 jmcomic 写完每张图的瞬间 `os.path.getsize` 累加累计字节，随 `extra` 透传 `bytes`/`images`。前端按累计字节增量算速度（EMA 平滑）。
- **删除扫目录测速**：`_watch_speed` 的每秒 `os.walk` + 逐文件 `getsize` 线程停用（既吃 CPU，又在搬运清空 TempCache 后读出 0 KB/s），函数保留为兼容存根。
- **重复下载拦截**：新增 `_is_jm_downloading()`，单本与批量下载都会拒绝「同一本已在下载中」的重复提交（原先只拦「已下载」，漏了「正在下载」这个真正的入口）。

### 验证
- `node --check`、`py_compile`、selftest（重写 `test_download_tuning()`：真实键/幽灵键清理/封顶/after_image 字节/两处重复拦截/前端字节测速/不再启动扫目录线程）、smoke 全绿。
- 端到端实测：新默认与旧配置迁移后，`decide_image_batch_count/decide_photo_batch_count` 均为 **8 / 2**（原 30 / 16）。

## v2.1.0 — 2026-10-09

> 关键功能重构（UI 不大改）：修「切换页面卡死」、提速下载、速度常驻显示。

### 1. 切换页面卡死（PJAX 局部刷新 · 根治）
- **侧栏改 PJAX**：`.side-nav .side-item` 点击被拦截（`pushState` 更新 URL + `popstate` 兜底），用 `fetch` 取目标页 HTML，`DOMParser` 抽出 `.main` 整体替换，**不再整页跳转**。原先每次点击都要重新拉 HTML + app.js + style.css 并重跑全部 init，pywebview 下明显卡顿。
- **重跑 init**：替换后调 `routeInit()` 重跑 4 个主页面 init；各 init 均为元素级绑定且带 DOM 守卫（元素不存在直接 return），新 DOM 上天然不重复。
- **定时器不再叠加（卡死主因之一）**：新增页面级清理表 `regCleanup` / `clearPageCleanups`，下载页的 `setInterval(refreshActive,1500)` / `setInterval(refreshHistory,8000)` 登记其中，PJAX 切走时 `clearInterval`。此前每来回一次下载页就多两个轮询，多个任务同时跑时 CPU/请求风暴。
- **顺带**：切页时关闭遗留 `.modal-overlay`；`.main` 加 `opacity` 过渡作轻量反馈；切回搜索页不再补拉 `enrich`（卡片自带 tags），避免多余网络往返。
- 阅读器（`/reader/<id>`，整页大图）仍走整页跳转，不进 PJAX。

### 2. 下载速度不及手机端
- **图片并发下限 `DOWNLOAD_WORKER_FLOOR = 12`**：原默认 `download.threading.max_workers=5` 偏低（PC 宽带下并发不足）。默认值改为走下限。
- **强制抬升老配置**：`_ensure_option_file` 读取已有 `jm_option.yml` 时，若 `max_workers < 12`（或 `batch_count < 30`）则抬到下限并回写。此前「不覆盖用户设置」，只改默认值对老用户无效——这是提速不生效的关键。`batch_count` 默认提到 30。

### 3. 下载速度不是一直显示
- **后端**：`_watch_speed` 由「每轮全量 `os.walk` + 每文件 `getsize`」改为**按路径缓存 `seen`、只对新增文件 `getsize`**，采样间隔 1s→1.5s，并对速度做**指数平滑**（`ema*0.6 + inst*0.4`）。原实现每 1s 对上万张图的目录逐个 `getsize`，是 CPU/GIL 大头（也是卡顿来源之一）。
- **前端**：`fmtSpeed(0)` 不再返回空串；进行中/取消中**一律显示速度**（`starting`/`preparing` 显示「测速中…」），不再因瞬时为 0 导致整段消失。

### 验证
- `node --check app.js`、`py_compile`、`selftest`（新增 PJAX/并发下限/测速契约断言）、`smoke` 全绿。

## v2.0.4 — 2026-10-09

> 切换页面保留原页面内容（补齐此前缺失的能力）：侧栏整页跳转改为「离开即存、回来即还原」。

### 背景
侧栏 `<a href="/search">` 等是 pywebview **整页跳转**（每个路由独立 Flask 模板），此前切到「书架」再切回「搜索」会丢搜索结果/输入框/滚动位置，且只有主题存了 localStorage。

### 改动
- **搜索页会话完整保留**：`searchState`（查询/范围/排序/标签模式/页码/结果卡片）写入 `sessionStorage['jm_lite_search_state']`。`renderCards` 每次渲染后落盘、`input` 输入即存；`initSearchPage` 进入时若无 `?kw=` 深链且存在已搜会话，则原样还原卡片 + 输入框 + 范围/排序控件 + `setCount()`，并恢复滚动。结果为客户端快照，重新搜索即刷新（符合预期）。
- **全页滚动位置保留**：`bindScrollKeep()` 在 `.main`（`overflow-y:auto` 滚动容器）滚动时节流存 `sessionStorage['jm_lite_scroll_' + pathname]`；搜索/书架/下载/设置各页初始渲染后 `restoreScroll()` 还原滚动位置。仅还原一次，不干扰后续刷新。
- 仅前端行为，后端/下载链路/启动能力不变；sessionStorage 随 webview 会话存在，重启 App 自然清空（首屏回到空态，符合预期）。

## v2.0.3 — 2026-10-09

> 卡片 UI 微调（对齐手机端「JM 轻量版」）：JM 号移到作者右侧 + 封面右下角透明下载按钮。

### 卡片信息布局
- **JM 号移到作者右侧**：搜索卡与书架卡的 meta 行由「作者」独占改为 `<作者> <JM号>`（书架卡保留「· N 页」），JM 号以次强调色呈现，与手机端一致。

### 封面下载按钮（透明轮廓）
- 封面包入 `.comic-card__coverwrap` 容器，右下角新增圆形下载按钮 `.card-dl`：
  - **透明背景 + 可见轮廓**：`background: transparent`，仅保留 `1.6px` 白色描边圆环 + 白色下载 SVG（带 `drop-shadow` 保证在亮色封面也清晰）；hover 时填充主题色。
  - **点击即下载**：搜索网格与书架网格的点击委托在最前拦截 `[data-dl]`，调 `startDownload(id, title)` 并 `stopPropagation`（不触发详情/进阅读器/拖拽/多选干扰），搜索与书架两处一致。
- 仅调整布局与样式，下载链路（v2.0.1）与启动（v2.0.2）能力不变。

## v2.0.2 — 2026-10-09

> 启动速度优化（不改动功能/UI）：窗口更快出现。

### 启动提速
- **JMCrawler 改为惰性单例**：此前 import `core.app` 时会同步构造 `JMCrawler`（加载 cover/detail 缓存等大 JSON），且 `DownloadManager` 又新建第二个实例（双倍 I/O），全部阻塞在窗口出现之前。现在 `get_jm_crawler()` 首次被搜索/下载/详情/订阅巡检调用时才构造，import 阶段只留轻量初始化（DB/缓存目录/配置），窗口更早弹出。
- **消除重复实例**：`DownloadManager` 不再在构造时建 `JMCrawler`，改为复用全局单例（首次下载/恢复时惰性取），少一次大缓存加载。
- **订阅巡检传惰性 getter**：`sub_service.schedule(get_jm_crawler)`，3 分钟后的首次巡检才真正构造爬虫。

### 说明
- 首次搜索/打开详情时仍会加载一次缓存（一次性，窗口已可见，体验无感）；后续命中内存缓存。
- 冷启动若仍偏慢，主要源于 onedir 打包下杀软逐个扫描解出的 DLL（沙箱无法测）；可选后续：`build/_build.py` 开启 UPX 或改 onefile 打包（有杀软误报风险，需真机验证）。

## v2.0.1 — 2026-10-09

> 下载优化（接续 Trae 的任务）：实时进度 / 速度 / 取消并删除；UI 与主题沿用 v2.0.0 不动。

### 下载进行时（优化）
- **实时速度**：后台线程采样 `TempCache` 下载目录字节增量，估算 MB/s（KB/s 兜底）并显示在进度条下方。
- **章节进度**：进度回调透传 `done/total`，进行中列表显示「X/Y 章」而非笼统百分比文本。
- **取消并删除**：进行中任务新增「取消」按钮——`POST /api/download/cancel/<id>` 置取消事件 → 下载线程在 `after_photo` 抛 `DownloadCancelled` 中断 → 清理 `TempCache` 临时目录 + 调 `comic_manager.delete_completely`（本地内容 + DB 记录 + 分类关联全清 + 清 LOCAL 位）+ 历史记 `cancelled`；取消中显示「取消中…」，完成后短暂展示「已取消并清理」再移出列表。

### 后端改动
- `_JmProgressCallback` 加 `cancel_check` 形参与 `DownloadCancelled` 异常；进度回调签名扩展 `extra={done,total}`。
- `download_manager` 三层 `download_comic → download_comic_async → _real_comic_download` 透传 `cancel_check` 与 `extra`，逐层 re-raise `DownloadCancelled`。
- `app.py`：`_update_progress` 接收 `extra` 落 `done/total`；新增 `_dl_cancel_events` 映射、`_watch_speed` 速度采样线程、`_cancel_download_cleanup` 取消清理；单本 / 批量下载创建 `cancel_event` 并启动速度线程。

## v2.0.0 — 2026-10-09

> 对齐手机端「JM 轻量版」（v1.12.0）：云同步 / 批量删除 / 回收站；UI 全面重做为 Material You 精致化。

### 新功能（对齐手机端）
- **云同步**：把「看过的漫画 JM 号」与自有同步服务器双向合并——打开详情 / 阅读器 / 下载 / 收藏 / 读完即入账本；换机重装后一键找回全部看过的 JM 号。服务器只存数字 ID + 时间戳（隐私最小化），本地为权威、幂等可重跑；启动时静默自动同步（距上次成功 ≥6 小时）。
- **书架批量删除**：点「选择」进多选模式——全选 / 未读 / 已读一键勾选，批量删除（逐本执行，单本失败不影响其余）。
- **回收站**：删除本地 = 移入回收站（保留账本与封面）；读完的书宽限 7 天后自动清理本地内容，期间重读自动续期；支持「恢复 / 重新下载 / 彻底删除」，入口在书架右上角（带待处理计数）。

### UI 全面重做（Material You 精致化）
- **新设计系统**：层级化 surface（4 级）+ 大圆角（8/12/16/22/28）+ 胶囊按钮 / 分段控件 / 芯片 / MD3 开关；动效全面升级（卡片悬停浮起、渐入、弹性、进度流光）。
- **侧栏**：渐变品牌标、导航药丸高亮 + 指示条、下载进行中徽标（实时计数）、底部署名与主题开关。
- **设置改版（按手机端入口）**：一级 = 外观 / 书架 / 搜索 / 阅读 / 下载 / 关于 六个入口卡（带当前值摘要）；二级页分类收纳——书架组含云同步与订阅巡检，搜索组含排序 / 屏蔽规则 / 黑名单，阅读组含章节提醒与**滚轮行为**（新增：以光标缩放 / 上下滚动），下载组含并发数与画质；改动即时保存，无需「保存」按钮。
- **阅读器**：新增章节选择浮层（点章节号弹出全章列表）、滚轮行为设置生效（滚动模式半页适配）、读完提示说明回收站语义。
- **全站**：搜索 / 书架 / 下载 / 阅读器 / 设置页面视觉统一（页头渐变标题、卡片、空态插画、骨架加载、详情模态、Toast）。

### 修复 / 打磨
- 详情页「页数」修正：改为展示「章节数」（jmcomic 无现成全站页数，逐章统计成本过高）。
- 关于页新增「已下载漫画占用 / 缓存占用」统计。
- /api/cover/downloaded 支持回收站保留的缓存封面回退。

### 使用说明
- 解压 `JMComicLite_v2.0.0_portable.zip` → 双击 `JMComicLite.exe`
- 需要 Windows 10/11（自带 WebView2 运行时）
- 首次启动在 exe 同级目录自动生成 `UserData/`（配置与下载存放处）
- 云同步：设置 → 书架 → 开启（服务器地址与密钥在设置中自行填写，两端协议一致）

### 已知问题
- 暂无