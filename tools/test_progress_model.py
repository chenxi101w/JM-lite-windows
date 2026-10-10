# -*- coding: utf-8 -*-
"""
进度模型契约测试（直驱 _JmProgressCallback，零网络零 fake 依赖）。

对治的问题：章节按「2 章一批」下载时，旧公式 frac = imgs_done/已开始章节页数
会在换批时分母跳大 → 进度回跳/停滞（用户实锤「一直 36%」）。
新公式：frac = (已完成章数 + 进行中章页数完成比) / 总章数 —— 批间连续、全程单调。

不变量（本文件锁死）：
  1. pct 全程单调不减
  2. 首个进度拍 = 20，末拍 = 80
  3. 每批开始后 pct 不低于该批起点值（批间零回跳）
  4. skip 大军（重下场景）也推进度；取消检查点在 before_image
运行：python tools/test_progress_model.py（退出码 0/1）
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.services.jm_crawler import _JmProgressCallback, DownloadCancelled  # noqa: E402

FAILED = []


def ok(cond, name):
    print(("[OK ] " if cond else "[FAIL] ") + name)
    if not cond:
        FAILED.append(name)


class P:
    def __init__(self, n):
        self._n = n

    def __len__(self):
        return self._n


class A:
    def __init__(self, n):
        self._n = n

    def __len__(self):
        return self._n


def make_file(tmp, size=100):
    p = os.path.join(tmp, "f.jpg")
    with open(p, "wb") as f:
        f.write(b"x" * size)
    return p


def drive(total_chapters, batches, tmp):
    """按批驱动：每批 (章数, 每章页数)。返回 pct 序列。"""
    pcts = []
    cb = _JmProgressCallback(lambda p, s, m, e=None: pcts.append(p) if e else None)
    cb.before_album(A(total_chapters))
    f = make_file(tmp)
    for (n_ch, pages) in batches:
        photos = [P(pages) for _ in range(n_ch)]
        for ph in photos:
            cb.before_photo(ph)
        for i in range(pages):
            for ph in photos:
                cb.before_image(None, f)
                cb.after_image(None, f)
        for ph in photos:
            cb.after_photo(ph)
    return pcts


def main():
    tmp = tempfile.mkdtemp()
    f = make_file(tmp)

    # ── 场景 1：3 批 × 2 章 × 10 页（旧公式回跳的典型案例）──
    pcts = drive(6, [(2, 10), (2, 10), (2, 10)], tmp)
    ok(pcts == sorted(pcts), "6 章 3 批：pct 全程单调不减（旧公式批间回跳 80→50）")
    ok(pcts[0] == 20 and pcts[-1] == 80, "首拍 20、末拍 80")
    # 批界不变量：每批末值（完成 2/4/6 章 → 40/60/80）一旦出现不得回落
    for boundary in (40, 60, 80):
        idx = pcts.index(boundary)
        ok(min(pcts[idx:]) >= boundary, f"批界 {boundary}% 出现后不回落到其下")

    # ── 场景 2：99 章小章节本（真实用户案例 454204）──
    pcts2 = drive(99, [(2, 5)] * 50 + [(1, 5)], tmp)   # 99 章、最后一批 1 章
    ok(pcts2 == sorted(pcts2), "99 章：全程单调不减")
    ok(pcts2[0] == 20 and pcts2[-1] == 80, "99 章：首 20 末 80")

    # ── 场景 3：skip 大军（重下：文件已存在，before_image 触发/after_image 不触发）──
    pcts3 = []
    cb3 = _JmProgressCallback(lambda p, s, m, e=None: pcts3.append((p, e)) if e else None)
    cb3.before_album(A(2))
    for i in range(2):
        cb3.before_photo(P(10))
    for i in range(20):                      # 全部 skip：只走 before_image
        cb3.before_image(None, f)
    for i in range(2):
        cb3.after_photo(P(10))
    seq3 = [p for p, e in pcts3]
    ok(seq3 == sorted(seq3) and seq3[-1] == 80, "重下全 skip：进度照常走到 80（不靠网络字节）")
    # 2 章一批且两章并发时，批内完成比最多到 0.5 → pct 到 50；完成后直跳 80
    ok(50 in seq3 and min(seq3[seq3.index(50):]) >= 50, "skip 场景批内插值照常（50 后不回落）")

    # ── 场景 4：取消检查点在 before_image（skip 段可即时取消）──
    cb4 = _JmProgressCallback(lambda *a, **k: None, cancel_check=lambda: True)
    cb4.before_album(A(1))
    cb4.before_photo(P(3))
    raised = False
    try:
        cb4.before_image(None, f)
    except DownloadCancelled:
        raised = True
    ok(raised, "before_image 抛 DownloadCancelled（skip 段可即时取消）")

    # ── 场景 5：after_image 异常安全（文件已被删/权限异常不炸）──
    cb5 = _JmProgressCallback(lambda *a, **k: None)
    cb5.before_album(A(1))
    cb5.before_photo(P(1))
    try:
        cb5.before_image(None, os.path.join(tmp, "不存在.jpg"))
        cb5.after_image(None, os.path.join(tmp, "不存在.jpg"))
        ok(True, "getsize 失败静默（不炸下载）")
    except Exception as e:
        ok(False, f"getsize 失败静默（异常：{e}）")

    if FAILED:
        print(f"\n失败 {len(FAILED)} 项")
        return 1
    print("\n进度模型契约全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
