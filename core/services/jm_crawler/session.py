# -*- coding: utf-8 -*-
"""JM 下载会话与进度回调（自 jm_crawler.py 拆出）。

取消异常、下载日志（JSONL）、每图/每章进度采样会话、进度回调、带钩子的 jmcomic 下载器工厂。"""

import json
import os
import threading
import time
from typing import List
from core.config import BASE_DIR

from core.logging_setup import get_logger

log = get_logger("jm_crawler")

# ── 下载日志（JSONL，一行一本，供后续分析下载速度惯性） ──────
# 字段刻意精简：jm_id / 时间 / 状态 / 耗时秒 / 章节数 / 总页数 /
# 实际下载图数 / 大小MB / 平均MB每秒 / 每秒MB采样数组。
DOWNLOAD_LOG_PATH = os.path.join(BASE_DIR, "logs", "download_log.jsonl")
_dl_log_lock = threading.Lock()

class DownloadCancelled(Exception):
    """下载被用户取消：在 jmcomic 回调中抛出以中断同步下载循环。"""
    pass

class _DownloadSession:
    """一次下载的记录器：每秒速度采样 + 结束落 JSONL 日志。

    download_comic 只管「下载」，本类管「记录」——采样线程纯内存读回调的
    字节计数（零 IO），无论 completed / cancelled / failed，finally 里
    finish() 都落一条日志。
    """

    def __init__(self, album_id: int, cb: "_JmProgressCallback"):
        self.album_id = album_id
        self.cb = cb
        self.status = "failed"
        self.samples: List[float] = []
        self._t0 = time.time()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        # 每秒采一次「该秒下载的 MB」（即瞬时 MB/s）
        last = 0
        while not self._stop.wait(1.0):
            cur = self.cb._bytes
            self.samples.append(round(max(0.0, cur - last) / 1048576, 3))
            last = cur

    def finish(self):
        """结束采样并落日志（线程安全、失败静默，绝不影响下载本体）。"""
        self._stop.set()
        try:
            self._thread.join(timeout=1.5)
        except Exception:
            pass
        self._write_log()

    def _write_log(self):
        try:
            cb = self.cb
            dur = max(0.1, time.time() - self._t0)
            rec = {
                "jm_id": self.album_id,
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": self.status,
                "duration_s": round(time.time() - self._t0, 1),
                "chapters": cb._total,
                "pages": cb._pages_total,
                "imgs": cb._images,
                "size_mb": round((cb._bytes + cb._skip_bytes) / 1048576, 2),
                "avg_mb_s": round(cb._bytes / dur / 1048576, 3),
                "samples_mb": self.samples,
            }
            os.makedirs(os.path.dirname(DOWNLOAD_LOG_PATH), exist_ok=True)
            with _dl_log_lock:
                with open(DOWNLOAD_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
        except Exception as e:
            log.warning(f"写下载日志失败: {e}")

class _JmProgressCallback:
    """下载进度收集器（由 _build_hooked_downloader 生成的子类转发钩子调用）。

    进度模型：全局「已完成图数 / 全本总页数」单一计数（锁保护）——
    imgs_done 只增不减 → pct 天然单调，章节并发下也无共享状态竞争。
    """

    def __init__(self, progress_callback, cancel_check=None):
        self._pc = progress_callback
        self._cancel_check = cancel_check
        self._lock = threading.Lock()
        self._total = 0         # 总章数
        self._done = 0          # 已完成章数
        self._pages_total = 0   # 已开始章节的总页数（before_photo 逐章累加）
        self._done_pages = 0    # 已完成章节的总页数（after_photo 累加，用于批进度）
        self._imgs_done = 0     # 全局已完成图数（skip 的图也算，见 before_image）
        self._bytes = 0         # 新下载字节（after_image 累加）
        self._skip_bytes = 0    # 已存在被跳过文件的大小（计入日志 size_mb）
        self._images = 0        # 真实下载图数

    def _maybe_cancel(self):
        if self._cancel_check and self._cancel_check():
            raise DownloadCancelled()

    def before_photo(self, photo):
        """逐章累计全本总页数（len(photo) = 该章图片数）。"""
        try:
            n = len(photo)
        except Exception:
            n = 0
        with self._lock:
            self._pages_total += n
        self._emit()

    def _emit(self):
        """推送进度快照。pct 映射 20~80%，**批间连续、全程单调**：

        frac = (已完成章数 + 当前进行中章的页数完成比) / 总章数

        推导（关键不变量）：章完成瞬间 done+1 且该章移出「进行中」批，
        (done + 1) / total ≡ (done + 该章页/该章页) / total —— 恒等连续。
        由此**无需全本总页数**（禁漫不提供）也能做到：
        - 章数做分母（全程恒定）→ 换批（2 章一批）不再回跳；
        - 章内页数比做分子微调 → 进度条在章内持续走动。
        """
        if not self._pc:
            return
        with self._lock:
            total, done = self._total, self._done
            pages, imgs = self._pages_total, self._imgs_done
            done_pages = self._done_pages
            new_bytes = self._bytes
            images = self._images
        if total > 0:
            batch_pages = pages - done_pages          # 进行中章的页数
            batch_imgs = max(0, imgs - done_pages)    # 进行中章已完成图数
            if batch_pages > 0:
                frac = min(1.0, (done + batch_imgs / batch_pages) / total)
            else:
                frac = min(1.0, done / total)
        elif pages > 0:                               # 兜底：总章数未知
            frac = min(1.0, imgs / pages)
        else:
            frac = 0.0
        pct = 20 + int(frac * 60)  # 映射到 20~80%
        if total:
            msg = f"下载 {done}/{total} 章 · 已下 {imgs}/{pages} 页"
        else:
            msg = f"已下 {imgs} 页" if imgs else "下载中"
        extra = {"done": done, "total": total,
                 "bytes": new_bytes, "images": images}
        try:
            self._pc(pct, "downloading", msg, extra)
        except Exception:
            pass

    def before_album(self, album):
        # len(album) = episode_list 长度（纯本地，零网络）；jmcomic 的
        # JmAlbumDetail 没有 photo_count 属性，page_count 对多章本恒为 0。
        try:
            total = len(album)
        except Exception:
            total = 0
        with self._lock:
            self._total = total
        self._emit()

    def before_image(self, image, img_save_path):
        """jmcomic 在「skip 判断之前」调用本钩子——两件事都在这里做：

        1. 取消检查点：重下同一本时，TempCache 里上次残留的已下完文件会被
           大批 skip，skip 路径不会触发 after_image → 没有这里的检查点，
           这一大段完全无响应（取消点不了一、进度也不走）。
        2. skip 图也算完成（_imgs_done +1），进度条照常走动。
        """
        self._maybe_cancel()
        with self._lock:
            self._imgs_done += 1
        try:
            sz = os.path.getsize(img_save_path)
        except OSError:
            sz = 0
        with self._lock:
            self._skip_bytes += sz
        self._emit()

    def after_image(self, image, img_save_path):
        """逐图落盘后累加真实下载字节（速度的数据源），并立即推进度。"""
        self._maybe_cancel()
        try:
            sz = os.path.getsize(img_save_path)
        except OSError:
            sz = 0
        with self._lock:
            self._images += 1
            self._bytes += sz
        self._emit()

    def after_photo(self, photo):
        self._maybe_cancel()
        try:
            n = len(photo)
        except Exception:
            n = 0
        with self._lock:
            self._done += 1
            self._done_pages += n
        self._emit()

    def after_album(self, album):
        try:
            self._pc(85, "processing", "章节下载完成，正在整理…")
        except Exception:
            pass

def _build_hooked_downloader(cb: "_JmProgressCallback"):
    """生成把 jmcomic 下载钩子转发给进度收集器的 JmDownloader 子类。

    硬约束：download_album 的 `callback` 参数只是**返回值回调**（下载结束后
    才被调用一次），不会注册进下载器钩子链——进度监听必须子类化
    JmDownloader 覆写钩子并经 `downloader=` 传入，且 super() 要保留
    （jmcomic 自身的 feature/统计机制挂在那里）。
    """
    from jmcomic.jm_downloader import JmDownloader

    class _HookedDownloader(JmDownloader):
        def before_album(self, album):
            cb.before_album(album)
            super().before_album(album)

        def before_photo(self, photo):
            cb.before_photo(photo)
            super().before_photo(photo)

        def before_image(self, image, img_save_path):
            cb.before_image(image, img_save_path)
            super().before_image(image, img_save_path)

        def after_image(self, image, img_save_path):
            cb.after_image(image, img_save_path)
            super().after_image(image, img_save_path)

        def after_photo(self, photo):
            cb.after_photo(photo)
            super().after_photo(photo)

        def after_album(self, album):
            cb.after_album(album)
            super().after_album(album)

    return _HookedDownloader
