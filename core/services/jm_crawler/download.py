# -*- coding: utf-8 -*-
"""下载主链路（自 jm_crawler.py 拆出）。

直驱 jmcomic 的下载（带回退 _simple_download）与封面落盘。"""

import io
import os
import time
from typing import Optional
from PIL import Image
from core.models.database import get_image_quality_params

from .session import DownloadCancelled, _DownloadSession, _JmProgressCallback, _build_hooked_downloader

from core.logging_setup import get_logger

log = get_logger("jm_crawler")

class DownloadMixin:
    """下载主链路（直驱 jmcomic，带回退）。"""
    def download_comic(self, album_id: int, progress_callback=None,
                       cancel_check=None) -> bool:
        """下载漫画到 TempCache/downloads/<id>（下载管理器负责后续搬运）。

        cancel_check: 可调用对象，返回 True 时中断下载（抛 DownloadCancelled）。
        结束时（无论成败/取消）把速度采样写入 JSONL 下载日志，供分析下载惯性。
        """
        cb = _JmProgressCallback(progress_callback, cancel_check)
        session = _DownloadSession(album_id, cb)
        try:
            if progress_callback:
                progress_callback(0, "starting", "开始下载...")

            download_dir = os.path.join(self.base_dir, "TempCache", "downloads", str(album_id))
            os.makedirs(download_dir, exist_ok=True)
            # 续下检测：TempCache 有残留 → 已下好的图会被 jmcomic 的 skip 自动跳过
            _exist_files = 0
            for _r, _d, fs in os.walk(download_dir):
                _exist_files += len(fs)

            if progress_callback:
                if _exist_files:
                    progress_callback(10, "preparing",
                                      f"续传：检测到已下 {_exist_files} 个文件，自动跳过已下部分...")
                else:
                    progress_callback(10, "preparing", "准备下载环境...")

            option = self._build_option()

            if progress_callback:
                progress_callback(30, "downloading", "正在获取漫画信息...")

            try:
                import jmcomic
                jmcomic.download_album(
                    album_id,
                    option=option,
                    downloader=_build_hooked_downloader(cb),  # 钩子子类：进度/取消/字节统计的唯一正道
                    check_exception=False,
                )
                if progress_callback:
                    progress_callback(80, "downloading", "漫画下载中...")
                time.sleep(2)
            except DownloadCancelled:
                raise
            except Exception as e:
                log.warning(f"JMComic 下载失败: {e}")
                ok = self._simple_download(album_id, progress_callback, cancel_check, cb)
                session.status = "completed" if ok else "failed"
                return ok

            if progress_callback:
                progress_callback(95, "processing", "下载完成，正在验证文件...")

            if not os.path.exists(download_dir):
                if progress_callback:
                    progress_callback(0, "error", "下载失败：目录未创建")
                return False

            # 只数真实文件：jmcomic 会先建 Pid 子目录，图片全失败时
            # os.listdir 也能看到子目录名 → 曾造成大量「假 completed」
            file_count = 0
            for _root, _dirs, fs in os.walk(download_dir):
                file_count += len(fs)
            if file_count == 0:
                if progress_callback:
                    progress_callback(0, "error", "下载失败：未产出任何图片文件")
                return False

            log.info(f"漫画 {album_id} 下载成功，文件数: {file_count}")
            if progress_callback:
                progress_callback(100, "completed", f"下载完成，共 {file_count} 个文件")
            session.status = "completed"
            return True

        except DownloadCancelled:
            # 取消必须继续向上抛：download_manager 三层都 re-raise，
            # 最终由 app._run_download_task 触发「取消并清理」；否则会被当成
            # 普通失败（历史记 failed、TempCache 不清理）。
            session.status = "cancelled"
            raise
        except Exception as e:
            log.warning(f"下载漫画失败 {album_id}: {e}")
            import traceback
            traceback.print_exc()
            if progress_callback:
                progress_callback(0, "error", f"下载失败: {str(e)}")
            return False
        finally:
            session.finish()

    def _simple_download(self, album_id: int, progress_callback=None,
                         cancel_check=None, cb=None) -> bool:
        """备用下载流程（同样挂进度钩子）。"""
        try:
            if cancel_check and cancel_check():
                raise DownloadCancelled()
            if progress_callback:
                progress_callback(40, "downloading", "使用备用方式下载...")

            option = self._build_option()
            client = option.build_jm_client()

            if cancel_check and cancel_check():
                raise DownloadCancelled()
            album = client.get_album_detail(album_id)
            if not album:
                log.warning(f"无法获取专辑 {album_id} 详情")
                return False

            if progress_callback:
                progress_callback(60, "downloading", "获取图片列表...")

            photo_detail = client.get_photo_detail(album_id)
            if not photo_detail:
                log.warning(f"无法获取照片详情 {album_id}")
                return False

            if progress_callback:
                progress_callback(80, "downloading", "下载漫画内容...")

            if cb is not None:
                dler = _build_hooked_downloader(cb)(option)
            else:
                import jmcomic
                dler = jmcomic.JmDownloader(option)
            dler.download_album(album_id)

            if progress_callback:
                progress_callback(95, "processing", "下载完成")
            return True

        except Exception as e:
            log.warning(f"备用下载失败 {album_id}: {e}")
            return False

    def _download_cover(self, cover_url: str, album_id: int) -> Optional[str]:
        """下载封面到本地缓存（带画质设置）。"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            from curl_cffi import requests as curl_requests
            response = curl_requests.get(cover_url, headers=headers, timeout=30)
            response.raise_for_status()

            cover_filename = f"cover_{album_id}.jpg"
            cover_path = os.path.join(self.temp_cache, cover_filename)

            image = Image.open(io.BytesIO(response.content))
            if image.mode == "RGBA":
                rgb_image = Image.new("RGB", image.size, (255, 255, 255))
                rgb_image.paste(image, mask=image.split()[3])
                image = rgb_image

            quality, subsampling = get_image_quality_params()
            image.save(cover_path, "JPEG", quality=quality, subsampling=subsampling)
            return cover_path

        except Exception as e:
            log.warning(f"下载封面失败 {album_id}: {e}")
            return None
