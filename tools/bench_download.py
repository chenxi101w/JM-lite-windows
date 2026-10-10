# -*- coding: utf-8 -*-
"""
下载速度基准（同环境对比不同 postman/并发配置）。

用法：python tools/bench_download.py [jm_id]
每组用独立临时目录（无 skip 缓存）真实下载同一本，输出时长与 MB/s。
"""
import copy
import json
import os
import sys
import tempfile
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import yaml  # noqa: E402
from core.services import jm_crawler as jc  # noqa: E402
from core.services.jm_crawler import JMCrawler  # noqa: E402

JM_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 1480569

GROUPS = [
    {"name": "旧默认 cffi(非session) 8x2 ", "postman": "curl_cffi", "image": 8, "photo": 2},
    {"name": "新默认 cffi_session    16x4 ", "postman": "curl_cffi_session", "image": 16, "photo": 4},
    {"name": "验算   cffi_session    24x6 ", "postman": "curl_cffi_session", "image": 24, "photo": 6},
]


def run_group(g):
    tmp = tempfile.mkdtemp(prefix="jm_bench_")
    obj = object.__new__(jc.JMCrawler)
    obj.base_dir = tmp
    obj.option_file = os.path.join(tmp, "jm_option.yml")

    content = JMCrawler._build_default_option_content(
        types.SimpleNamespace(base_dir=tmp))
    content = copy.deepcopy(content)
    content["client"]["postman"] = {"type": g["postman"], "meta_data": {}}
    content["download"]["threading"] = {"image": g["image"], "photo": g["photo"]}
    with open(obj.option_file, "w", encoding="utf-8") as f:
        f.write(yaml.safe_dump(content, allow_unicode=True))

    jc.DOWNLOAD_LOG_PATH = os.path.join(tmp, "log.jsonl")
    t0 = time.time()
    ok = obj.download_comic(JM_ID, progress_callback=lambda *a, **k: None)
    dur = time.time() - t0

    rec = {}
    if os.path.exists(jc.DOWNLOAD_LOG_PATH):
        lines = open(jc.DOWNLOAD_LOG_PATH, encoding="utf-8").read().strip().splitlines()
        if lines:
            rec = json.loads(lines[-1])
    size = rec.get("size_mb", 0)
    imgs = rec.get("imgs", 0)
    return {
        "name": g["name"], "ok": ok, "dur": round(dur, 1),
        "size_mb": size, "imgs": imgs,
        "mb_s": round(size / dur, 2) if dur else 0,
        "img_s": round(imgs / dur, 1) if dur else 0,
        "samples": rec.get("samples_mb", []),
    }


def main():
    print(f"基准本：jm={JM_ID}")
    results = []
    for g in GROUPS:
        print(f"[bench] 运行 {g['name']} ...", flush=True)
        try:
            r = run_group(g)
        except Exception as e:
            r = {"name": g["name"], "ok": False, "dur": 0, "size_mb": 0,
                 "imgs": 0, "mb_s": 0, "img_s": 0, "samples": [], "err": str(e)[:100]}
        results.append(r)
        s = r["samples"]
        peak = max(s) if s else 0
        print(f"    {'OK' if r['ok'] else 'FAIL'}  {r['dur']:>6.1f}s  "
              f"{r['size_mb']:>6.1f}MB  {r['mb_s']:>5.2f}MB/s  {r['img_s']:>4.1f}图/s  "
              f"峰值{r['peak'] if False else round(peak,2)}MB/s")

    print("\n── 汇总 ──")
    for r in results:
        s = r["samples"]
        print(f"{r['name']}  {r['dur']:>6.1f}s  {r['mb_s']:>5.2f}MB/s  {r['img_s']:>4.1f}图/s  "
              f"采样中位{round(sorted(s)[len(s)//2],2) if s else 0}MB/s")


if __name__ == "__main__":
    main()
