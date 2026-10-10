# -*- coding: utf-8 -*-
"""实机验证脚本：对部署版 JMComicLite 做端到端验证（启动→功能→重启持久化→关闭）。

用法（项目根）:  .venv-build\\Scripts\\python.exe tools\\verify_live.py
"""
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:28889"
EXE = r"D:\Game\JMComicLite\JMComicLite.exe"

results = []


def check(cond, label):
    results.append((bool(cond), label))
    print(("[OK ] " if cond else "[FAIL] ") + label)


def http(method, path, body=None, timeout=90, raw=False):
    req = urllib.request.Request(BASE + path, method=method)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data=data, timeout=timeout) as r:
        content = r.read()
        if raw:
            return r.status, content
        try:
            return r.status, json.loads(content)
        except Exception:
            return r.status, content


def start_app():
    subprocess.run(["taskkill", "/F", "/IM", "JMComicLite.exe"], capture_output=True)
    time.sleep(2)
    proc = subprocess.Popen([EXE])
    time.sleep(15)
    return proc


def main():
    proc = start_app()

    # ── 1. 启动与基础 ──
    try:
        st, r = http("GET", "/api/ping", timeout=15)
        check(st == 200 and r.get("ok"), "启动：ping OK（v%s）" % r.get("version"))
    except Exception as e:
        check(False, "启动：ping 失败 %s" % e)
        proc.terminate()
        return 1

    st, r = http("GET", "/api/about", timeout=15)
    check(r.get("success"), "基础：关于接口 OK（数据目录 %s）" % r["data"].get("base_dir"))

    # ── 2. 设置写入与回读 ──
    http("POST", "/api/settings", {"max_concurrent_downloads": "5", "theme": "dark",
                                   "hide_downloaded_in_search": "gray"}, timeout=15)
    st, r = http("GET", "/api/settings", timeout=15)
    ok = r["data"].get("max_concurrent_downloads") == "5" and r["data"].get("theme") == "dark"
    check(ok, "设置：并发/主题写入并回读 OK")

    # ── 3. 搜索连通性 ──
    search_ok = False
    first = None
    data_list = []
    try:
        st, r = http("GET", "/api/search/keyword?keyword=%E4%B8%AD%E6%96%87&page=1", timeout=90)
        data_list = r.get("data") or []
        search_ok = r.get("success") and len(data_list) > 0
        first = data_list[0] if search_ok else None
        check(search_ok, "搜索：关键词返回 %d 条（首条 id=%s）" % (len(data_list), first and first.get("id")))
    except Exception as e:
        check(False, "搜索：请求失败（网络不可达？）%s" % e)

    # ── 4. 黑名单（在线过滤 / 离线增删） ──
    if search_ok and first:
        aid = first.get("id")
        http("POST", "/api/blocklist", {"type": "work", "value": str(aid)}, timeout=15)
        st, r = http("GET", "/api/search/keyword?keyword=%E4%B8%AD%E6%96%87&page=1", timeout=90)
        ids = [c.get("id") for c in (r.get("data") or [])]
        check(aid not in ids, "黑名单：屏蔽作品后从搜索结果消失（id=%s）" % aid)
    else:
        st, r = http("POST", "/api/blocklist", {"type": "author", "value": "验证测试作者"}, timeout=15)
        check(r.get("success"), "黑名单：离线添加 OK")
    # 清空黑名单
    st, bl = http("GET", "/api/blocklist", timeout=15)
    for b in bl.get("data") or []:
        http("DELETE", "/api/blocklist/%s" % b["id"], timeout=15)
    st, bl = http("GET", "/api/blocklist", timeout=15)
    check(len(bl.get("data") or []) == 0, "黑名单：清理完成")

    # ── 5. 订阅（在线）/ 离线增删 ──
    if search_ok and first and first.get("author"):
        author = first["author"]
        st, r = http("POST", "/api/subscriptions", {"author": author}, timeout=15)
        sid = r.get("id")
        check(bool(sid), "订阅：添加作者 OK")
        try:
            st, r = http("POST", "/api/subscriptions/poll", timeout=240)
            check(r.get("success"), "订阅：手动巡检完成（检查 %s 位 / 新增 %s 条）"
                  % (r.get("checked"), r.get("added_new")))
        except Exception as e:
            check(False, "订阅：巡检超时 %s" % e)
        st, r = http("GET", "/api/sub_updates", timeout=15)
        check(r.get("success"), "订阅：新作记录接口 OK（%d 条）" % len(r.get("data") or []))
        http("DELETE", "/api/subscriptions/%s" % sid, timeout=15)
    else:
        st, r = http("POST", "/api/subscriptions", {"author": "验证测试作者"}, timeout=15)
        check(r.get("success"), "订阅：离线添加 OK")
        st, r = http("GET", "/api/subscriptions", timeout=15)
        for s in r.get("data") or []:
            http("DELETE", "/api/subscriptions/%s" % s["id"], timeout=15)

    # ── 6. 分类（离线） ──
    st, r = http("POST", "/api/categories", {"name": "验证分类A"}, timeout=15)
    cid = (r.get("data") or {}).get("id")
    check(bool(cid), "分类：创建 OK")
    if cid:
        http("PUT", "/api/comic/999901/categories", {"category_ids": [cid]}, timeout=15)
        st, r = http("GET", "/api/categories?tree=1", timeout=15)
        node = next((n for n in r["data"] if n.get("id") == cid), None)
        check(bool(node) and node.get("count", 0) >= 1, "分类：树内计数 OK（count=%s）" % (node and node.get("count")))
        st, r = http("DELETE", "/api/categories/%s" % cid, {"reassign_to": None}, timeout=15)
        check(r.get("success"), "分类：非空删除（重分配）OK")

    # ── 升级 v2.0.0：云同步（实测）/ 回收站 ──
    st, r = http("GET", "/api/sync/status", timeout=15)
    sd = (r or {}).get("data") or {}
    check(r.get("success") and str(sd.get("server_url", "")).startswith("http"),
          "云同步：状态接口 OK（服务器 %s）" % sd.get("server_url"))

    http("POST", "/api/settings", {"sync_enabled": "1"}, timeout=15)
    try:
        st, r = http("POST", "/api/sync/now", timeout=90)
        if r.get("success"):
            check(True, "云同步：实测同步成功（拉回 %s · 推上 %s · 服务器新增 %s）"
                  % (r.get("pulled"), r.get("pushed"), r.get("new_on_server")))
        else:
            check(False, "云同步：实测同步失败 - %s" % r.get("message"))
    except Exception as e:
        check(False, "云同步：实测异常 %s" % e)

    st, r = http("GET", "/api/recycle", timeout=30)
    check(r.get("success") is True, "回收站：列表接口 OK（当前 %d 项）" % len(r.get("data") or []))

    # ── 7. 下载 + 阅读端到端（已有本地样本则跳过重复下载，只验阅读链路） ──
    jid = None
    st, r = http("GET", "/api/downloaded", timeout=30)
    existing = r.get("data") or []

    if existing:
        jid = existing[0]["id"]
        check(True, "下载：已有本地样本 id=%s（跳过重复下载，直接验证阅读链路）" % jid)
    elif search_ok:
        best = None
        fallback = None
        for c in [x for x in data_list if isinstance(x.get("id"), int)][:8]:
            try:
                st, d = http("GET", "/api/detail/%s" % c["id"], timeout=60)
                if not d.get("success"):
                    continue
                dd = d.get("data") or {}
                size = int(dd.get("pages") or 0) or int(dd.get("chapters") or 0)
                if fallback is None:
                    fallback = (c["id"], size)
                if size > 0 and (best is None or size < best[1]):
                    best = (c["id"], size)
            except Exception:
                continue
        sample = best or fallback
        if sample:
            jid = sample[0]
            st, r = http("POST", "/api/download/%s" % jid, {}, timeout=30)
            check(r.get("success"), "下载：任务启动 OK（id=%s）" % jid)
            did = r.get("download_id")
            done = False
            t0 = time.time()
            while time.time() - t0 < 600:
                time.sleep(6)
                try:
                    st, p = http("GET", "/api/download/progress/%s" % did, timeout=15)
                except Exception:
                    done = True
                    break
                if not p.get("success"):
                    done = True
                    break
                d = p.get("data") or {}
                if d.get("status") in ("error", "completed"):
                    done = d.get("status") == "completed"
                    break
            check(done, "下载：完成并落库")
            st, r = http("GET", "/api/downloaded", timeout=30)
            check(any(c["id"] == jid for c in r.get("data") or []), "下载：已进入书架")
        else:
            check(False, "下载：无可用测试样本（网络不可达或结果为空）")
    else:
        check(False, "下载：无可用测试样本（网络不可达或结果为空）")

    # 阅读链路（对样本执行）
    if jid:
        st, r = http("GET", "/api/read/%s" % jid, timeout=30)
        check(r.get("success"), "阅读：打开成功（%d 个章节）" % len((r.get("data") or {}).get("chapters") or []))
        if r.get("success"):
            chap = urllib.parse.quote(str(r["data"]["current_chapter"]))
            try:
                st, img = http("GET", "/api/comic/%s/page/1?chapter=%s" % (jid, chap), timeout=30, raw=True)
                check(isinstance(img, bytes) and len(img) > 1000, "阅读：第一页图片 %d bytes" % len(img))
            except Exception as e:
                check(False, "阅读：第一页图片失败 %s" % e)
            http("POST", "/api/read/%s/progress" % jid, {"page": 2}, timeout=15)
            st, r2 = http("GET", "/api/read/%s" % jid, timeout=15)
            check(int((r2.get("data") or {}).get("read_progress") or 0) == 2, "阅读：进度落库并回读 OK")
        try:
            st, cover = http("GET", "/api/cover/downloaded/%s" % jid, timeout=20, raw=True)
            check(isinstance(cover, bytes) and len(cover) > 500, "下载：本地封面 %d bytes" % len(cover))
        except Exception as e:
            check(False, "下载：本地封面失败 %s" % e)

    # ── 8. 重启持久化 ──
    proc.terminate()
    time.sleep(3)
    proc = start_app()
    try:
        st, r = http("GET", "/api/settings", timeout=15)
        check(r["data"].get("theme") == "dark", "重启：设置持久化 OK（theme=dark）")
        st, r = http("GET", "/api/downloaded", timeout=30)
        if jid:
            check(any(c["id"] == jid for c in r.get("data") or []), "重启：书架数据持久化 OK")
        else:
            check(r.get("success"), "重启：书架接口 OK")
    except Exception as e:
        check(False, "重启：检查失败 %s" % e)

    proc.terminate()

    print("=" * 56)
    failed = [l for ok, l in results if not ok]
    if failed:
        print("结果：失败 %d / %d 项" % (len(failed), len(results)))
        for l in failed:
            print("  ✗ " + l)
        return 1
    print("结果：全部通过（%d 项）" % len(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())