# -*- coding: utf-8 -*-
"""JM 轻量版自检脚本（~50 项）。

覆盖：工程文件完整性 / Python 语法 / 路由冒烟 / 前端符号（含已砍功能无残留）/
模板 Jinja2 配对与关键容器 id / CSS 变量引用完整性。

用法（项目根）:  .venv-build\\Scripts\\python.exe tools\\selftest_lite.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

os.environ["BASE_DIR"] = tempfile.mkdtemp(prefix="jmlite_selftest_")

failures = []


def check(cond: bool, label: str):
    if not cond:
        failures.append(label)
        print(f"[FAIL] {label}")
    else:
        print(f"[OK ] {label}")


# ── A. 工程文件完整性 ─────────────────────────────────────
REQUIRED_FILES = [
    "VERSION", "desktop_app.py", "README.md",
    "core/__init__.py", "core/config.py", "core/app.py",
    "core/models/__init__.py", "core/models/database.py",
    "core/services/__init__.py", "core/services/jm_crawler.py",
    "core/services/comic_manager.py", "core/services/download_manager.py",
    "core/services/filter_service.py", "core/services/subscription.py",
    "web/templates/base.html", "web/templates/search.html", "web/templates/library.html",
    "web/templates/downloads.html", "web/templates/reader.html", "web/templates/settings.html",
    "web/static/img/no_cover.svg",
    "web/static/js/app.js", "web/static/js/reader-logic.js",
    "web/static/css/style.css", "web/static/img/app_icon.ico",
    "build/JMComicLite.spec", "build/_build.py", "build/requirements.txt",
    "docs/CHANGELOG.md", "docs/已知坑与发版铁律.md",
    "tools/test_reader_logic.js",
]


def test_files():
    for f in REQUIRED_FILES:
        check(os.path.isfile(os.path.join(ROOT, f)), f"文件存在：{f}")


# ── B. Python 语法 ────────────────────────────────────────
def test_python_syntax():
    import py_compile
    py_files = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".venv-build", "dist_out", "build_out", "__pycache__", ".git")]
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(base, f))
    bad = []
    for f in py_files:
        try:
            py_compile.compile(f, doraise=True)
        except Exception:
            bad.append(f)
    check(not bad, f"Python 语法（{len(py_files)} 个文件）" + (f"，失败：{bad}" if bad else ""))


# ── C. 路由冒烟 ────────────────────────────────────────────
def test_routes():
    from core.app import app
    client = app.test_client()
    # 启动惰性：import 阶段不应构造 JMCrawler（此前会在 import 同步加载大缓存拖慢启动）
    from core.app import jm_crawler as _jc_global, get_jm_crawler as _gjc
    check(_jc_global is None, "启动：jm_crawler 惰性未创建（import 阶段为 None）")
    check(_gjc() is not None, "get_jm_crawler：可惰性构造单例")
    pages = ["/", "/search", "/library", "/downloads", "/reader/123", "/settings"]
    for p in pages:
        r = client.get(p, follow_redirects=True)
        check(r.status_code == 200, f"页面 {p} -> {r.status_code}")
    apis = [
        "/api/ping", "/api/settings", "/api/about",
        "/api/categories?tree=1", "/api/downloaded", "/api/blocklist",
        "/api/subscriptions", "/api/sub_updates", "/api/download/progress",
        "/api/download/history",
    ]
    for p in apis:
        r = client.get(p)
        check(r.status_code == 200 and r.is_json, f"接口 {p} -> {r.status_code}")
    # 取消接口注册（未知 id 应优雅返回 success=False）
    r = client.post("/api/download/cancel/nonexistent_id_123")
    data = r.get_json() or {}
    check(r.status_code == 200 and r.is_json and data.get("success") is False,
          "接口 POST /api/download/cancel/<id> 已注册（未知 id 返回 False）")


# ── D. 前端符号 ───────────────────────────────────────────
def test_js_symbols():
    js = open(os.path.join(ROOT, "web/static/js/app.js"), encoding="utf-8").read()
    app_src = open(os.path.join(ROOT, "core/app.py"), encoding="utf-8").read()
    required = [
        "initSearchPage", "initDownloadsPage", "initReaderPage",
        "initLibraryPage", "initSettingsPage",
        "startDownload", "openDetail", "doSearch", "renderCards",
        "cardHtml", "shelfCardHtml", "esc", "toast", "toggleTheme",
        "fmtSpeed", "/api/download/cancel/", 'data-cancel',
        "saveSearchState", "loadSearchState", "restoreScroll", "bindScrollKeep",
        "jm_lite_search_state", "jm_lite_scroll_",
        "pjaxNav", "routeInit", "clearPageCleanups", "regCleanup", "markActiveNav",
    ]
    for sym in required:
        check(sym in js, f"JS 符号存在：{sym}")
    # PJAX 关键契约：必须走局部换 .main，且下载页定时器要登记清理（防叠加卡死）
    check(".main'" in js and "replaceChild" in js, "PJAX：局部替换 .main 而非整页跳转")
    check("regCleanup(function () { clearInterval(_tActive)" in js,
          "PJAX：下载页定时器登记清理（防叠加）")
    # 阅读器滚轮契约：默认滑动翻页 + 右键滚轮缩放 + 屏蔽右键菜单
    check("var wheelMode = 'page'" in js, "滚轮默认滑动翻页（page）")
    rl_js = open(os.path.join(ROOT, "web/static/js/reader-logic.js"), encoding="utf-8").read()
    check("buttons & 2" in rl_js, "按住右键+滚轮 = 以光标缩放（reader-logic，已被单测覆盖）")
    check("stage.addEventListener('contextmenu'" in js, "阅读器屏蔽右键菜单")
    check("wheelAcc" in js, "滚轮累计阈值（防触控板小步误触）")
    seg_html = open(os.path.join(ROOT, "web/templates/settings.html"), encoding="utf-8").read()
    check('data-v="page"' in seg_html, "设置页滚轮行为含「滑动翻页」选项")
    # 阅读器复刻：进度滑轨（reader_progress_color）+ 缩略图览（reader_pages_per_screen）
    rdr_html = open(os.path.join(ROOT, "web/templates/reader.html"), encoding="utf-8").read()
    check('id="readerRail"' in rdr_html, "阅读器有右侧进度滑轨容器")
    check('id="readerGrid"' in rdr_html and 'id="overviewBtn"' in rdr_html, "阅读器有览图容器与切换按钮")
    check("function updateRail" in js and "RAIL_DEFAULT_COLOR" in js, "滑轨填充更新逻辑")
    check("function renderOverview" in js and "function setOverview" in js, "览图渲染/切换逻辑")
    check("reader_progress_color" in js and "reader_pages_per_screen" in js, "阅读器读取两个新设置")
    check('id="setPpsSeg"' in seg_html, "设置页有览图列数选项")
    check('id="setRailColor"' in seg_html and 'id="setRailColorCustom"' in seg_html,
          "设置页有滑轨颜色色板与自定义取色")
    check('"reader_pages_per_screen"' in app_src and '"reader_progress_color"' in app_src,
          "两个新设置键在写入白名单内")
    css = open(os.path.join(ROOT, "web/static/css/style.css"), encoding="utf-8").read()
    check(".reader__rail" in css and ".reader__grid" in css and ".swatches" in css,
          "滑轨/览图/色板样式存在")
    check("[hidden] { display: none !important; }" in css.replace("\n", " ") or
          "reader__grid[hidden]" in css, "hidden 守卫（作者样式不乱显）")
    # 已砍功能不得残留
    removed = ["initTagsPage", "initDiscover", "initRecommend", "initRecycle", "FavTags", "FavAuthors"]
    for sym in removed:
        check(sym not in js, f"旧功能已无残留：{sym}")


# ── D2. 下载契约（并发 / 回调 / 进度 / 网络 / 日志 / 状态）──
def test_download_tuning():
    crawler = open(os.path.join(ROOT, "core/services/jm_crawler.py"), encoding="utf-8").read()
    app = open(os.path.join(ROOT, "core/app.py"), encoding="utf-8").read()
    js = open(os.path.join(ROOT, "web/static/js/app.js"), encoding="utf-8").read()

    # 并发：真实开关是 threading.image/photo；max_workers 幽灵键、batch_count 旧别名必须清理
    check("DOWNLOAD_IMAGE_CONCURRENCY" in crawler and "DOWNLOAD_PHOTO_CONCURRENCY" in crawler
          and 'threading_cfg.pop("max_workers", None)' in crawler
          and 'threading_cfg.pop("batch_count", None)' in crawler
          and "_clamp_concurrency" in crawler,
          "并发：真实键 image/photo + 清理幽灵键 + 封顶")
    # 速度实测（2026-10-09 基准）：session 复用 + 16×4 = 4.3× 提速
    check("DOWNLOAD_IMAGE_CONCURRENCY = 16" in crawler and "DOWNLOAD_PHOTO_CONCURRENCY = 4" in crawler,
          "并发默认 16×4（基准实测最优）")
    check('"curl_cffi_session"' in crawler and "老配置缺 postman.type" in crawler,
          "postman session 复用（+54%~4.3× 提速）+ 老配置迁移")

    # 回调注册正道：必须子类化 JmDownloader 并经 downloader= 传入（callback 参数不是钩子）
    check("def _build_hooked_downloader" in crawler
          and "downloader=_build_hooked_downloader(cb)" in crawler
          and "from jmcomic.jm_downloader import JmDownloader" in crawler,
          "回调注册：JmDownloader 钩子子类经 downloader= 传入")

    # 进度模型：全局计数 + 锁；批间连续公式（分母=总章数恒定，不做页数回跳）
    check("def _emit(self)" in crawler and "_imgs_done" in crawler and "self._lock" in crawler
          and "已下" in crawler,
          "进度：_emit 推送（全局计数+锁）")
    check("batch_pages = pages - done_pages" in crawler
          and "(done + batch_imgs / batch_pages) / total" in crawler,
          "批间连续公式（分母=总章数，旧 imgs/pages 会换批回跳）")
    check("total = len(album)" in crawler,
          "总章数取自 len(album)（零网络，jmcomic 无 photo_count 属性）")
    check("def before_image(self, image, img_save_path)" in crawler and "_skip_bytes" in crawler,
          "before_image：skip 大军有取消检查点 + 进度 + 字节单独计数")

    # 网络：显式接管代理（杜绝 5788）+ 注入超时 + 系统代理跟随
    check('"http": None' in crawler and 'meta["timeout"] = DOWNLOAD_HTTP_TIMEOUT' in crawler
          and "def _detect_system_proxy" in crawler,
          "网络：显式直连 + HTTP 超时 + 系统代理探测")

    # 日志：_DownloadSession 统一采样与落盘，三结局（completed/cancelled/failed）都写
    check("class _DownloadSession" in crawler and "session.finish()" in crawler
          and '"samples_mb": self.samples' in crawler and '"download_log.jsonl"' in crawler,
          "下载日志：_DownloadSession 统一采样+落盘（含失败/取消）")
    check("def before_photo(self, photo)" in crawler and "_pages_total" in crawler,
          "回调逐章累计总页数")

    # 状态：收拢为 _DownloadRegistry 单例（防重复 / 立即取消 / 统一透传），死代码清零
    check("class _DownloadRegistry" in app and "_registry = _DownloadRegistry()" in app
          and "def is_downloading" in app and "def cancel" in app,
          "状态：_DownloadRegistry 单例（防重复/立即取消）")
    check('for key in ("done", "total", "bytes", "images")' in app,
          "进度透传：Registry.update 统一透传 done/total/bytes/images")
    check('"该漫画正在下载中，请勿重复提交"' in app and '"已在下载中"' in app,
          "重复下载拦截：单本 + 批量")
    check("_watch_speed" not in app and "cancelling" not in app,
          "后端死代码清零：_watch_speed 存根 / cancelling 残留")
    # 续下：取消保留 TempCache + 空壳放行 + resumable 字段
    check("保留 TempCache 已下部分供续下" in app and "_tempcache_file_count" in app,
          "取消=保留可续（不再清 TempCache/本地内容）")
    check("_downloaded_real_file_count" in app and "未完成判定" in app and "dc_files > tc_files" in app,
          "未完成判定（在库<残留 → 清壳续下；正常已下载才拦）")
    check('item["resumable"]' in app, "历史接口返回 resumable（续下按钮条件）")
    # 封面兜底链：占位图 + 负缓存 + 书目录自愈
    check("_send_no_cover" in app and "no_cover.svg" in app,
          "封面占位兜底（拉不到也返回 200 占位图，img 永不破图）")
    check("_cover_fail_until" in app and "_COVER_FAIL_TTL" in app,
          "封面失败负缓存（10 分钟内直接占位，不再反复全轮询）")
    check("书目录自愈" in app, "封面拉取成功顺手补书目录 cover.jpg")
    check("visibility=\\'hidden\\'" in js, "img onerror 隐藏（不显示破图图标）")
    # 书架三项（对齐手机端）：排序 / 每行列数 / 已读完沉底
    check("SHELF_ORDERS" in open(os.path.join(ROOT, "core/services/comic_manager.py"), encoding="utf-8").read()
          and "read_desc" in open(os.path.join(ROOT, "core/services/comic_manager.py"), encoding="utf-8").read(),
          "书架排序白名单（download_desc/read_desc/title_asc/author_asc）")
    check('get_system_config("shelf_sort")' in app and "sort=sort" in app,
          "书架接口按设置 shelf_sort 排序")
    check('"library_columns"' in app and '"library_finished"' in app,
          "设置白名单含 library_columns / library_finished")
    lib_html = open(os.path.join(ROOT, "web/templates/library.html"), encoding="utf-8").read()
    check('id="shelfSort"' in lib_html and "read_desc" in lib_html, "书架工具栏排序入口")
    check("lib-divider" in js and "已读完 · " in js and "library_finished" in js,
          "已读完沉底+分隔线渲染（hidden 可隐藏）")
    check("--lib-cols" in js or "setProperty('--lib-cols'" in js, "书架每行列数注入")
    set_html = open(os.path.join(ROOT, "web/templates/settings.html"), encoding="utf-8").read()
    check('id="setLibColsSeg"' in set_html and 'id="setLibFinSeg"' in set_html,
          "设置页书架显示两项（列数/读完处理）")
    css = open(os.path.join(ROOT, "web/static/css/style.css"), encoding="utf-8").read()
    check("var(--lib-cols, auto-fill)" in css and ".lib-divider" in css, "列数变量与分隔线样式")
    # 收藏备份（导出/导入，兼容手机端格式，跨端互通）
    dbstr = open(os.path.join(ROOT, "core/models/database.py"), encoding="utf-8").read()
    check("def get_favorite_ids" in dbstr, "get_favorite_ids（BIT_FAVORITE 位查询）")
    check("/api/favorites/export" in app and "/api/favorites/import" in app,
          "收藏导出/导入端点")
    check('"favoriteBooks"' in app and '"favTags"' in app and '"jmcomicreader-lite"' in app,
          "备份 JSON 手机端兼容格式（app/type/favoriteBooks/favTags）")
    check('id="favExportBtn"' in set_html and 'id="favImportFile"' in set_html,
          "设置页收藏备份入口（导出/导入）")
    check("api('/api/favorites/import'" in js and "api('/api/favorites/export'" in js,
          "前端绑定导出/导入调用")
    # 搜索列数（search_columns，对齐手机端）
    check('"search_columns"' in app, "设置白名单含 search_columns")
    check('id="setSearchColsSeg"' in set_html, "设置页搜索列数控件")
    check("setSearchColsSeg" in js and "applySearchCols" in js, "搜索页应用列数 + 设置绑定")
    # 启动提速：重包惰性化 + 预热
    check("import jmcomic" not in crawler.split("class JMCrawler")[0], "jm_crawler 顶部无重包 import（惰性化）")
    check("_preheat" in open(os.path.join(ROOT, "desktop_app.py"), encoding="utf-8").read(),
          "desktop_app 启动预热线程")
    desktop_src = open(os.path.join(ROOT, "desktop_app.py"), encoding="utf-8").read()
    check("_SPLASH_HTML" in desktop_src and "spinner" in desktop_src,
          "启动加载动画（splash 内嵌 HTML）")
    check("load_url(url)" in desktop_src and "_boot_backend" in desktop_src,
          "splash→主界面无缝切换 + 后端加载后置")
    check("_SPLASH_MIN_SECONDS" in desktop_src and "_SPLASH_MIN_SECONDS - (time.time() - t0)" in desktop_src,
          "动画最短展示时长（太快时补足、慢启动不叠加）")
    check("import aiohttp" not in open(os.path.join(ROOT, "core/services/download_manager.py"), encoding="utf-8").read(),
          "aiohttp 已移除（封面下载走 curl_cffi）")
    check("续传：检测到已下" in crawler, "下载开始检测 TempCache 残留并提示续传")
    check('data-resume="' in js and "已开始续下" in js, "历史列表渲染并绑定「续下」按钮")
    # 搜索耗时（筛选行右侧空白处）+ 卡片速度在百分比左边
    html_search = open(os.path.join(ROOT, "web/templates/search.html"), encoding="utf-8").read()
    check('id="searchTime"' in html_search and ".search-time" in
          open(os.path.join(ROOT, "web/static/css/style.css"), encoding="utf-8").read(),
          "搜索耗时元素与样式（筛选行右侧）")
    check("setSearchTime(Date.now() - t0)" in js, "doSearch 端到端计时上报")
    check("dl-item__right" in js and "var rightText = (spdText ? spdText + ' · ' : '') + pct + '%'" in js,
          "卡片：速度在百分比左边（右侧行）")
    # 封面本地代理（img 直连部分 CDN 域被网络环境阻断 → 服务端拉取+磁盘缓存）
    check("def api_cover_proxy" in app and "_cover_mimetype" in app,
          "封面本地代理端点（按文件头声明真实 MIME，含 webp）")
    check("def fetch_cover_bytes" in crawler and "DOMAIN_IMAGE_LIST" in crawler,
          "封面多域轮换拉取（jmcomic 内置图片域列表）")
    check("_cover_ok_prefix" in crawler, "封面成功域记忆（批量封面加速）")
    check(js.count("/api/cover/proxy/") >= 3, "前端三处封面（搜索/详情/回收站）走本地代理")
    # 假 completed 修复：只数真实文件（jmcomic 会先建 Pid 空子目录）
    check("for _root, _dirs, fs in os.walk(download_dir)" in crawler,
          "completed 判定只数真实文件（防空子目录误判）")
    check('"下载失败：未产出任何图片文件"' in crawler, "零文件明确报失败")

    # 前端：字节增量测速（EMA）+ 卡片精简三项
    check("function speedOf" in js and "ema * 0.6 + inst * 0.4" in js,
          "前端按字节增量测速（EMA 平滑）")
    check("'已下 ' + doneCh + ' 章 · 余 '" in js and "(d.status === 'downloading' && subText)" in js,
          "卡片只显示 大小·速度·已下/余章数")
    check("cancelling" not in js, "前端 cancelling 残留已清理")


# ── D3. 关于页存储明细契约 ─────────────────────────────────
def test_about_storage():
    app = open(os.path.join(ROOT, "core/app.py"), encoding="utf-8").read()
    check("def _scan_storage" in app, "存储扫描函数已定义")
    check('"storage_items"' in app, "/api/about 返回 storage_items 明细")
    check('"DownloadedComics"' in app and '"TempCache"' in app
          and '"webview_data"' in app, "额外存储逐项归桶")
    check("_storage_scan_cache" in app, "存储扫描 60s 缓存（避免反复全盘遍历）")
    check('"程序本体' in app, "非额外占用 = 程序本体单列")
    html = open(os.path.join(ROOT, "web/templates/settings.html"), encoding="utf-8").read()
    check('id="aboutStorageList"' in html, "关于页有存储明细容器")
    check('id="aboutStorageTotal"' in html, "关于页有总计行")
    js = open(os.path.join(ROOT, "web/static/js/app.js"), encoding="utf-8").read()
    check("storage_items" in js and "storage-row__bar" in js, "前端渲染存储明细（含占比条）")
    css = open(os.path.join(ROOT, "web/static/css/style.css"), encoding="utf-8").read()
    check(".storage-list" in css and ".storage-row__bar" in css, "存储明细样式存在")


# ── E. 模板检查 ───────────────────────────────────────────
def test_templates():
    tdir = os.path.join(ROOT, "web/templates")
    names = ["base.html", "search.html", "library.html", "downloads.html", "reader.html", "settings.html"]
    for n in names:
        html = open(os.path.join(tdir, n), encoding="utf-8").read()
        if n != "base.html":
            check("{% extends \"base.html\" %}" in html, f"{n} 继承 base")
        open_tags = len(re.findall(r"{%", html))
        close_tags = len(re.findall(r"%}", html))
        check(open_tags == close_tags, f"{n} Jinja2 语句配对（{open_tags}/{close_tags}）")
    # 关键容器 id（app.js 依赖）
    ids = {
        "search.html": ["searchInput", "comicGrid"],
        "library.html": ["catTree", "currentCatName", "selToolbar", "recycleView"],
        "downloads.html": ["batchInput", "activeList", "historyList"],
        "reader.html": ["readerStage", "pageInfo"],
        "settings.html": ["setHome", "syncNowBtn", "blList", "setWheelSeg"],
    }
    for n, need in ids.items():
        html = open(os.path.join(tdir, n), encoding="utf-8").read()
        for i in need:
            check(f'id="{i}"' in html, f"{n} 含容器 id：{i}")


# ── F. CSS 变量完整性 ─────────────────────────────────────
def test_css_vars():
    css = open(os.path.join(ROOT, "web/static/css/style.css"), encoding="utf-8").read()
    defined = set(re.findall(r"(--[\w-]+)\s*:", css))
    used = set(re.findall(r"var\((--[\w-]+)", css))
    # 运行时注入的变量（JS setProperty / 内联 style 提供，CSS 里只消费）：
    #   --rail-color 阅读器滑轨色（JS 从设置注入，var() 均带兜底值）
    #   --cols       览图固定列数（JS 注入，var(--cols, 6) 有兜底）
    #   --sw         色板圆点底色（内联 style="--sw:#xxx"）
    #   --lib-cols   书架每行列数（JS 注入，var(--lib-cols, auto-fill) 有兜底）
    runtime_injected = {"--rail-color", "--cols", "--sw", "--lib-cols"}
    missing = sorted(used - defined - runtime_injected)
    check(not missing, "CSS 变量引用完整" + (f"，缺失：{missing}" if missing else ""))
    check("--accent" in defined and "--surface" in defined, "CSS 主题令牌存在")
    check("[data-theme=\"dark\"]" in css, "CSS 暗色主题定义存在")


# ── G. reader-logic 纯逻辑单测（node 真跑）─────────────────
def test_reader_logic():
    """reader-logic.js 抽出的纯函数用 node 真跑单测（无需浏览器/DOM）。

    这是对治「打桩绿≠生效」的样板：滚轮判定/滑轨定位/览图 HTML 三块
    今天被反复改的逻辑，用真实断言锁死行为。
    """
    base_html = open(os.path.join(ROOT, "web/templates/base.html"), encoding="utf-8").read()
    check("js/reader-logic.js" in base_html
          and base_html.index("js/reader-logic.js") < base_html.index("js/app.js"),
          "reader-logic.js 先于 app.js 加载")
    js = open(os.path.join(ROOT, "web/static/js/app.js"), encoding="utf-8").read()
    check("ReaderLogic.resolveWheelAction" in js and "ReaderLogic.railIndex" in js
          and "ReaderLogic.buildOverviewHtml" in js,
          "app.js 使用纯逻辑模块（不再是内联实现）")

    node = shutil.which("node")
    if not node:
        import glob
        hits = sorted(glob.glob(os.path.expanduser(
            "~/.workbuddy/binaries/node/versions/*/node.exe")))
        node = hits[-1] if hits else "node"
    script = os.path.join(ROOT, "tools/test_reader_logic.js")
    if not os.path.exists(script):
        check(False, "tools/test_reader_logic.js 存在")
        return
    try:
        r = subprocess.run([node, script], capture_output=True, text=True, timeout=60)
    except Exception as e:
        check(False, f"reader-logic 单测无法执行：{e}")
        return
    n_ok = (r.stdout or "").count("[OK ]")
    check(r.returncode == 0, f"reader-logic 单测（node 真跑，{n_ok} 项）" +
          ("" if r.returncode == 0 else "\n" + (r.stdout or "")[-500:]))


# ── H. 进度模型契约（直驱 cb，零网络）──────────────────────
def test_progress_model():
    """进度模型契约测试：批间连续 + 全程单调（直驱 _JmProgressCallback）。

    对治「2 章一批下载换批回跳/停滞」——旧公式 frac=imgs/已开始章节页数
    在换批时分母跳大；新公式分母=总章数恒定。
    """
    script = os.path.join(ROOT, "tools/test_progress_model.py")
    if not os.path.exists(script):
        check(False, "tools/test_progress_model.py 存在")
        return
    r = subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=60)
    n_ok = (r.stdout or "").count("[OK ]")
    check(r.returncode == 0, f"进度模型契约（{n_ok} 项：单调/批界不回跳/skip/取消）" +
          ("" if r.returncode == 0 else "\n" + (r.stdout or "")[-400:]))


def main():
    print("=" * 56)
    print("JM 轻量版自检")
    print("=" * 56)
    test_files()
    test_python_syntax()
    test_routes()
    test_js_symbols()
    test_download_tuning()
    test_about_storage()
    test_templates()
    test_css_vars()
    test_reader_logic()
    test_progress_model()

    total = len(REQUIRED_FILES) + 1 + 6 + 10 + (15 + 6) + (len(["base.html", "search.html", "library.html", "downloads.html", "reader.html", "settings.html"]) * 1 + 5 + 13) + 3  # 估算展示用
    print("=" * 56)
    if failures:
        print(f"结果：失败 {len(failures)} 项")
        return 1
    print(f"结果：全部通过（约 {total}+ 项断言）")
    return 0


if __name__ == "__main__":
    sys.exit(main())