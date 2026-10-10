# -*- coding: utf-8 -*-
"""冒烟测试：路由可达性 + 模板渲染 + 设置白名单 + 搜索链路基础能力。

用法（项目根）:  .venv-build\\Scripts\\python.exe tools\\smoke_test.py
用临时 BASE_DIR 跑，不污染工程目录；每次全新建库顺带验证 init_database 幂等。
不依赖外网：只测参数校验、同义词扩展、黑名单过滤、封面本地构造。
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

# 必须在 import core.* 之前指定临时数据目录
os.environ["BASE_DIR"] = tempfile.mkdtemp(prefix="jmlite_smoke_")

from core.app import app  # noqa: E402

PAGE_ROUTES = ["/", "/search", "/library", "/downloads", "/reader/123", "/settings"]
API_ROUTES = ["/api/ping", "/api/settings"]

failures = []


def check(cond: bool, label: str):
    mark = "OK " if cond else "FAIL"
    print(f"[{mark}] {label}")
    if not cond:
        failures.append(label)


def main():
    client = app.test_client()

    # ── 页面 / 基础接口 ──
    for path in PAGE_ROUTES:
        r = client.get(path, follow_redirects=True)
        check(r.status_code == 200, f"页面 {path} -> {r.status_code}")

    for path in API_ROUTES:
        r = client.get(path)
        check(r.status_code == 200 and r.is_json, f"接口 {path} -> {r.status_code}")

    # ── 设置白名单 ──
    r = client.post("/api/settings", json={"max_concurrent_downloads": "5", "evil_key": "x"})
    cfg = (r.get_json() or {}).get("data", {})
    check(cfg.get("max_concurrent_downloads") == "5", "设置白名单：允许键写入成功")
    check("evil_key" not in cfg, "设置白名单：非法键被忽略")

    # ── M2：搜索参数校验（不触网） ──
    for path, label in [
        ("/api/search/keyword", "空关键词"),
        ("/api/search/tags", "空标签"),
        ("/api/search/author", "空作者"),
    ]:
        r = client.get(path)
        data = r.get_json() or {}
        check(r.status_code == 200 and data.get("success") is False, f"搜索参数校验：{label}被拒")

    # ── M2：同义词扩展（硬约束，防误删） ──
    from core.services.filter_service import postprocess_results, expand_tags
    ex = expand_tags(["巨乳"])
    check("爆乳" in ex and "大奶" in ex, "同义词扩展：巨乳 → " + ",".join(ex))

    # ── M2：黑名单写入与搜索过滤 ──
    from core.models.database import add_block, get_blocked_sets, normalize_author
    add_block("author", "测试作者")
    sets = get_blocked_sets()
    check(normalize_author("测试作者") in sets["authors"], "黑名单：作者入库并可读取")
    res = postprocess_results([
        {"id": 1, "author": "测试作者", "tags": ["a"]},
        {"id": 2, "author": "正常作者", "tags": ["b"]},
    ])
    check(len(res) == 1 and res[0]["id"] == 2, "黑名单：搜索后处理剔除拉黑作者")

    # ── M2：封面 URL 本地构造（无网络请求） ──
    r = client.get("/api/cover/123")
    data = r.get_json() or {}
    check(r.status_code == 200 and data.get("success"), "封面接口：本地构造 URL 可用")

    # ── M3：下载接口基础（不触网） ──
    r = client.get("/api/download/progress")
    data = r.get_json() or {}
    check(r.status_code == 200 and data.get("success") is True and data.get("data") == {},
          "下载：进行中列表初始为空")

    r = client.get("/api/download/history")
    data = r.get_json() or {}
    check(r.status_code == 200 and data.get("success") is True, "下载：历史列表接口可用")

    r = client.post("/api/download/batch", json={"ids": []})
    data = r.get_json() or {}
    check(data.get("success") is False, "下载：批量空列表被拒")

    # ── M3：取消接口注册（未知 id 优雅返回 False） ──
    r = client.post("/api/download/cancel/nonexistent_id_123")
    data = r.get_json() or {}
    check(r.status_code == 200 and data.get("success") is False,
          "下载：取消接口已注册（未知 id 返回 False）")

    # ── M3：comic_status 位运算 ──
    from core.models.database import (
        BIT_FAVORITE, BIT_LOCAL, get_comic_status, set_status_bits,
    )
    set_status_bits(999001, BIT_LOCAL)
    set_status_bits(999001, BIT_FAVORITE)
    st = get_comic_status(999001)
    check(bool(st & BIT_LOCAL) and bool(st & BIT_FAVORITE), "状态位：LOCAL + FAVORITE 置位可用")
    set_status_bits(999001, clear=BIT_LOCAL)
    st2 = get_comic_status(999001)
    check(not (st2 & BIT_LOCAL) and bool(st2 & BIT_FAVORITE), "状态位：清 LOCAL 保留 FAVORITE")

    # ── M4：阅读接口（不触网） ──
    r = client.get("/api/read/999999")
    data = r.get_json() or {}
    check(data.get("success") is False, "阅读：未下载漫画被拒")

    r = client.post("/api/read/999999/progress", json={"page": 3})
    data = r.get_json() or {}
    check(data.get("success") is True, "阅读：进度上报接口可用")

    from core.models.database import BIT_FINISHED
    r = client.post("/api/status/999003/finished", json={"finished": True})
    st3 = get_comic_status(999003)
    check((r.get_json() or {}).get("success") and bool(st3 & BIT_FINISHED), "阅读：标记读完置位可用")
    client.post("/api/status/999003/finished", json={"finished": False})
    st4 = get_comic_status(999003)
    check(not (st4 & BIT_FINISHED), "阅读：取消读完清位可用")

    # ── M5：书架 / 分类（不触网） ──
    r = client.get("/api/downloaded")
    data = r.get_json() or {}
    check(r.status_code == 200 and data.get("success") is True and data.get("data") == [],
          "书架：已下载列表初始为空")

    r = client.post("/api/categories", json={"name": "测试分类"})
    cid = ((r.get_json() or {}).get("data") or {}).get("id")
    check(bool(cid), "分类：创建成功")

    r = client.get("/api/categories?tree=1")
    tree = (r.get_json() or {}).get("data") or []
    check(any(n.get("id") == cid for n in tree), "分类：树中包含新分类")

    r = client.put("/api/comic/999004/categories", json={"category_ids": [cid]})
    r2 = client.get("/api/comic/999004/categories")
    check((r.get_json() or {}).get("success") and (r2.get_json() or {}).get("data") == [cid],
          "分类：漫画归类读写可用")

    r = client.delete(f"/api/categories/{cid}", json={"reassign_to": None})
    check((r.get_json() or {}).get("success"), "分类：非空分类删除（移入未归类）成功")
    r2 = client.get("/api/comic/999004/categories")
    check((r2.get_json() or {}).get("data") == [], "分类：删除后漫画关联已清")

    # 收藏切换
    r = client.post("/api/status/999005/favorite", json={"favorite": True})
    check((r.get_json() or {}).get("success") and bool(get_comic_status(999005) & BIT_FAVORITE),
          "书架：收藏置位可用")

    # ── M6：订阅 / 黑名单（不触网） ──
    r = client.post("/api/blocklist", json={"type": "author", "value": "屏蔽测试作者"})
    bid = (r.get_json() or {}).get("id")
    check(bool(bid), "黑名单：添加成功")
    r = client.get("/api/blocklist")
    check(any(b.get("id") == bid for b in ((r.get_json() or {}).get("data") or [])), "黑名单：列表可读")
    r = client.delete(f"/api/blocklist/{bid}")
    check((r.get_json() or {}).get("success"), "黑名单：删除成功")

    r = client.post("/api/subscriptions", json={"author": "订阅测试作者"})
    sid = (r.get_json() or {}).get("id")
    check(bool(sid), "订阅：添加成功")
    r = client.get("/api/subscriptions")
    check(any(s.get("id") == sid for s in ((r.get_json() or {}).get("data") or [])), "订阅：列表可读")
    r = client.post(f"/api/subscriptions/{sid}/clear-new")
    check((r.get_json() or {}).get("success"), "订阅：清零新作计数可用")
    r = client.delete(f"/api/subscriptions/{sid}")
    check((r.get_json() or {}).get("success"), "订阅：取消成功")

    r = client.get("/api/about")
    check((r.get_json() or {}).get("success"), "关于：版本与数据目录接口可用")

    # ── 升级：云同步（离线检查，不触网） ──
    r = client.get("/api/sync/status")
    sd = (r.get_json() or {}).get("data") or {}
    check(r.status_code == 200 and str(sd.get("server_url", "")).startswith("http"),
          "云同步：状态接口与预填地址 OK")
    check(bool(sd.get("token_masked")), "云同步：密钥预填（遮罩返回）OK")

    # ── 升级：回收站全流程（假 id 走账本） ──
    from core.models.database import touch_comic_status
    touch_comic_status(999006, title="回收测试")
    r = client.get("/api/recycle")
    rd = r.get_json() or {}
    check(r.status_code == 200 and rd.get("success") is True, "回收站：列表接口可用")
    check(rd.get("grace_days") == 7, "回收站：宽限期 7 天")

    r = client.delete("/api/delete/999006")
    check((r.get_json() or {}).get("success") is True, "回收站：删除 = 移入回收站 OK")
    r = client.get("/api/recycle")
    items = (r.get_json() or {}).get("data") or []
    check(any(i.get("id") == 999006 for i in items), "回收站：条目出现在列表中")

    r = client.post("/api/recycle/999006/restore")
    check((r.get_json() or {}).get("success") is True, "回收站：恢复 OK")
    r = client.get("/api/recycle")
    check(all(i.get("id") != 999006 for i in (r.get_json() or {}).get("data") or []),
          "回收站：恢复后不在列表")

    r = client.delete("/api/recycle/999006")
    check((r.get_json() or {}).get("success") is True, "回收站：彻底删除 OK")

    print(f"\n结果：{'全部通过' if not failures else '失败 ' + str(len(failures)) + ' 项'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())