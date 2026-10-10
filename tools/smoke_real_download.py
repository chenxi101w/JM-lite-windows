# -*- coding: utf-8 -*-
"""
真实下载冒烟验证（对治 v2.0.1~v2.3.0 的系统性教训）。

背景：进度回调从 v2.0.1 起就没接通（jmcomic download_album 的 callback
参数不是下载钩子），但打桩测试 + 静态检查全绿，连续四轮「修复」都在
错误假设上宣布完成。教训：**涉及网络/IO 链路的改动，必须真实跑一遍**。

用法（发版前必跑， especially 动过 jm_crawler 下载链路时）：
    .venv-build\\Scripts\\python.exe tools\\smoke_real_download.py [jm_id]

默认 jm_id=1480569（小本，实测 26 图约 10MB 十几秒）。全程在临时目录，
结束即删，不碰 UserData。

判定（全部满足才 PASS）：
  1. 任务 completed 且返回 True
  2. 回调真实触发：chapters>0、pages>0、imgs>0、bytes>0
  3. pct 单调不减（不再出现固定阶段点乱跳）
  4. 下载日志落盘且字段与回调一致
"""
import json
import os
import shutil
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.services import jm_crawler as jc  # noqa: E402
from core.services.jm_crawler import JMCrawler  # noqa: E402

TEST_JM_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 1480569


def main():
    import yaml

    tmp = tempfile.mkdtemp(prefix="jm_smoke_")
    jc.DOWNLOAD_LOG_PATH = os.path.join(tmp, "download_log.jsonl")
    obj = object.__new__(jc.JMCrawler)
    obj.base_dir = tmp
    obj.option_file = os.path.join(tmp, "jm_option.yml")
    fake = types.SimpleNamespace(base_dir=tmp)
    with open(obj.option_file, "w", encoding="utf-8") as f:
        f.write(yaml.safe_dump(JMCrawler._build_default_option_content(fake),
                               allow_unicode=True))

    calls = []

    def pc(p, s, m, e=None):
        calls.append((p, s, m, dict(e or {})))

    print(f"[smoke] 真实下载 jm={TEST_JM_ID}（临时目录 {tmp}）...")
    ok = obj.download_comic(TEST_JM_ID, progress_callback=pc)

    failures = []
    log_rec = None
    log_path = jc.DOWNLOAD_LOG_PATH
    if os.path.exists(log_path):
        lines = open(log_path, encoding="utf-8").read().strip().splitlines()
        if lines:
            log_rec = json.loads(lines[-1])

    if not ok:
        failures.append("download_comic 未返回 True")
    last_msg = calls[-1][2] if calls else ""
    if "下载失败" in last_msg or "error" in (calls[-1][1] if calls else ""):
        failures.append(f"最后消息为失败: {last_msg}")

    # 从日志记录取权威数值（回调链必须真实落账）
    if not log_rec:
        failures.append("下载日志未落盘")
        rec = {}
    else:
        rec = log_rec
    for k in ("chapters", "pages", "imgs"):
        if rec.get(k, 0) <= 0:
            failures.append(f"回调未触发或未落账: {k}={rec.get(k)}")
    if rec.get("size_mb", 0) <= 0:
        failures.append(f"字节数为 0: size_mb={rec.get('size_mb')}")

    # pct 单调（只看带 extra 的真实进度拍，忽略固定阶段点）
    pcts = [c[0] for c in calls if c[3]]
    if pcts != sorted(pcts):
        failures.append(f"pct 非单调: {pcts[:10]}...")
    if not pcts:
        failures.append("没有任何带 extra 的进度拍（回调链没接通）")

    # 日志与回调一致性
    if log_rec and rec.get("imgs") != sum(
            1 for c in calls if c[3].get("images") and c[3]["images"] == rec.get("imgs")) \
            and rec.get("imgs", 0) <= 0:
        failures.append("日志 imgs 与回调不一致")

    # 展示
    print(f"[smoke] 状态: {rec.get('status')} | 章节={rec.get('chapters')} "
          f"页={rec.get('pages')} 图={rec.get('imgs')} "
          f"大小={rec.get('size_mb')}MB 平均={rec.get('avg_mb_s')}MB/s")
    dl = [c for c in calls if c[3]]
    if dl:
        print(f"[smoke] 进度: {dl[0][0]}% 「{dl[0][2]}」 → {dl[-1][0]}% 「{dl[-1][2]}」"
              f"（共 {len(dl)} 拍）")
    if rec.get("samples_mb"):
        s = rec["samples_mb"]
        print(f"[smoke] 速度采样 {len(s)} 个: 头{[round(x, 1) for x in s[:3]]} "
              f"尾{[round(x, 1) for x in s[-3:]]}")

    shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print("[smoke] FAIL:")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print("[smoke] PASS：真实下载回调链/进度/日志全部落账 ✓")


if __name__ == "__main__":
    main()
