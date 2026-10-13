#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
JM 轻量版 桌面启动入口。

启动本地 Flask 服务并用原生桌面窗口承载页面；所有用户数据（数据库 / 下载 /
缓存）统一放到 exe 同级 UserData/ 目录，更新程序时只覆盖 exe 与 appdata/，
用户数据不受影响。
"""

import io
import os
import socket
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
import webbrowser
import ctypes
from pathlib import Path

from werkzeug.serving import make_server
from core.logging_setup import get_logger

log = get_logger("desktop")


APP_NAME = "JMComicLite"
WINDOWS_APP_ID = "JMComicLite.Desktop"
WINDOW_TITLE = "JM 轻量版"
WINDOW_WIDTH = 1360
WINDOW_HEIGHT = 900
WINDOW_MIN_SIZE = (980, 680)

# 与旧版 JMComicReader（28888）分开：过渡期两个应用可能同时运行，固定端口
# 保证 localStorage / WebView2 存储不因端口变化而丢失。
DEFAULT_PORT = 28889

# 启动加载动画（内嵌 HTML，零外部依赖 + 深浅色自适应）——窗口立即出现，
# 后端在后台线程加载，就绪后同窗口无缝切到主界面。
_SPLASH_HTML = """<!doctype html><html><head><meta charset="utf-8">
<style>
  :root { color-scheme: light dark; }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { height:100vh; display:flex; flex-direction:column; align-items:center;
         justify-content:center; background:#f5f6fa; color:#5a6478;
         font-family: system-ui,-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;
         -webkit-user-select:none; user-select:none; }
  @media (prefers-color-scheme: dark) { body { background:#14161c; color:#aab2c5; } }
  .logo { width:88px; height:88px; border-radius:24px; display:flex; align-items:center;
          justify-content:center; background:linear-gradient(135deg,#7B6FE0,#9B8CF0);
          box-shadow:0 12px 34px rgba(123,111,224,.35); animation:breathe 2.4s ease-in-out infinite; }
  .logo svg { width:46px; height:46px; stroke:#fff; }
  @keyframes breathe { 0%,100% { transform:scale(1); } 50% { transform:scale(1.06); } }
  .title { margin-top:24px; font-size:17px; font-weight:700; letter-spacing:.6px; }
  .spinner { width:26px; height:26px; margin-top:28px; border-radius:50%;
             border:3px solid rgba(123,111,224,.22); border-top-color:#7B6FE0;
             animation:spin .85s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }
  .hint { margin-top:14px; font-size:12.5px; opacity:.72; }
</style></head><body>
  <div class="logo"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
    stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12"/><path d="M7 10l5 5 5-5"/>
    <path d="M5 21h14"/></svg></div>
  <div class="title">JM 轻量版</div>
  <div class="spinner"></div>
  <div class="hint">正在启动…</div>
</body></html>"""

# 加载动画最短展示时长（秒）——定稿「自适应」= 0：
#   启动快（热启动 ~0.6s）→ 一闪而过、直接进界面（不为动画付一秒）；
#   启动慢（冷启动/杀软扫描）→ 动画自然播放、起「有反馈」掩护作用。
# 如需强制保底展示（快速启动也看完整动画），把此值改为如 1.5 即可。
_SPLASH_MIN_SECONDS = 0

_BOOT_ERROR_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  body { height:100vh; display:flex; flex-direction:column; align-items:center;
         justify-content:center; gap:12px; background:#f5f6fa; color:#5a6478;
         font-family:system-ui,'Microsoft YaHei',sans-serif; }
  @media (prefers-color-scheme: dark) { body { background:#14161c; color:#aab2c5; } }
  b { font-size:16px; } p { font-size:13px; opacity:.75; }
</style></head><body>
  <b>启动失败</b><p>后端服务未能就绪。请查看 UserData/startup_error.log 后重试。</p>
</body></html>"""


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def get_exec_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_default_user_base_dir() -> Path:
    env_base_dir = os.environ.get("BASE_DIR")
    if env_base_dir:
        return Path(env_base_dir).expanduser().resolve()
    if is_frozen() and os.name == "nt":
        # 打包后：数据目录 = exe 同级的 UserData（与运行时 appdata/ 分离，
        # 便于单独备份；更新只覆盖 exe + appdata 不丢数据）。
        return get_exec_dir() / "UserData"
    return get_exec_dir()


def configure_runtime_env() -> Path:
    """创建运行时目录并把路径写入环境变量，供 core.config 读取。"""
    base_dir = get_default_user_base_dir()
    download_dir = base_dir / "DownloadedComics"
    temp_cache_dir = base_dir / "TempCache"
    backend_dir = base_dir / "core"

    download_dir.mkdir(parents=True, exist_ok=True)
    temp_cache_dir.mkdir(parents=True, exist_ok=True)
    backend_dir.mkdir(parents=True, exist_ok=True)

    os.environ["BASE_DIR"] = str(base_dir)
    os.environ["DOWNLOAD_DIR"] = str(download_dir)
    os.environ["TEMP_CACHE_DIR"] = str(temp_cache_dir)
    return base_dir


def _is_port_free(port: int) -> bool:
    """用 bind 探测端口是否空闲（比 connect_ex 更稳：不产生出站流量，
    不会被火绒/卡巴等杀软对本地回环连接的拦截拖慢 ~1s/次）。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


def get_or_create_port(base_dir: Path) -> int:
    """复用上次使用的端口；被占用或首次运行时使用默认端口并写回 .app_url。"""
    port_file = base_dir / ".app_url"
    saved = None
    try:
        if port_file.exists():
            saved = int(port_file.read_text().strip())
    except Exception:
        pass
    for candidate in (saved, DEFAULT_PORT):
        if candidate and candidate > 0 and _is_port_free(candidate):
            port_file.write_text(str(candidate))
            return candidate
    # 都不可用：随机端口兜底
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    port_file.write_text(str(port))
    return port


def configure_windows_app_id():
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 原生预启动窗（Win32 ctypes，零额外依赖）
#
# 启动链路：run_desktop → 先弹原生窗（秒级可见，消除点开到 splash 弹出的空白期）
#           → import webview → 内嵌 splash → webview.start 初始化 WebView2
#           → load_url 主界面。
#
# 内嵌 splash 出现在 import webview *之后*，因此点开到 splash 弹出之间仍有
# 一段纯黑屏 / 无响应期。这里在 import webview *之前* 用 Win32 直接弹一个原生窗，
# 把那段空白期变成「正在启动…」，体感从「点了没反应」变成「秒弹窗」。
#
# 任何异常都静默降级为「无原生 splash」，绝不阻塞主流程。
# ---------------------------------------------------------------------------
class NativeSplash:
    def __init__(self, title="JM 轻量版", hint="正在启动…"):
        self.hwnd = None
        self._thread = None
        self._wndproc_cb = None
        self._close_requested = False
        self._title = title
        self._hint = hint
        if os.name != "nt":
            return
        try:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        except Exception:
            self.hwnd = None

    # ---- Win32 常量 ----
    _CS_HREDRAW = 0x2
    _CS_VREDRAW = 0x1
    _WS_POPUP = 0x80000000
    _WS_VISIBLE = 0x10000000
    _WS_EX_TOPMOST = 0x8
    _WM_DESTROY = 0x2
    _WM_PAINT = 0xF
    _WM_CLOSE = 0x10
    _IDC_ARROW = 32512
    _COLOR_WINDOW = 5
    _DT_CENTER = 0x1
    _DT_SINGLELINE = 0x20
    _TRANSPARENT = 1
    _NULL_PEN = 8
    _SM_CXSCREEN = 0
    _SM_CYSCREEN = 1

    def _run(self):
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            WNDPROC = ctypes.WINFUNCTYPE(
                ctypes.c_long, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p
            )

            class _WNDCLASSEXW(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.c_uint),
                    ("style", ctypes.c_uint),
                    ("lpfnWndProc", ctypes.c_void_p),
                    ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int),
                    ("hInstance", ctypes.c_void_p),
                    ("hIcon", ctypes.c_void_p),
                    ("hCursor", ctypes.c_void_p),
                    ("hbrBackground", ctypes.c_void_p),
                    ("lpszMenuName", ctypes.c_wchar_p),
                    ("lpszClassName", ctypes.c_wchar_p),
                    ("hIconSm", ctypes.c_void_p),
                ]

            class _RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            class _PAINTSTRUCT(ctypes.Structure):
                _fields_ = [
                    ("hdc", ctypes.c_void_p),
                    ("fErase", ctypes.c_int),
                    ("rcPaint", _RECT),
                    ("fRestore", ctypes.c_int),
                    ("fIncUpdate", ctypes.c_int),
                    ("rgbReserved", ctypes.c_byte * 32),
                ]

            self._wndproc_cb = WNDPROC(self._wndproc)

            hinst = kernel32.GetModuleHandleW(None)
            cls = _WNDCLASSEXW()
            cls.cbSize = ctypes.sizeof(cls)
            cls.style = self._CS_HREDRAW | self._CS_VREDRAW
            cls.lpfnWndProc = ctypes.cast(self._wndproc_cb, ctypes.c_void_p)
            cls.hInstance = hinst
            cls.hCursor = user32.LoadCursorW(0, self._IDC_ARROW)
            cls.hbrBackground = ctypes.c_void_p(self._COLOR_WINDOW + 1)
            cls.lpszClassName = "JMComicLiteSplash"
            if not user32.RegisterClassExW(ctypes.byref(cls)):
                return

            sw = user32.GetSystemMetrics(self._SM_CXSCREEN)
            sh = user32.GetSystemMetrics(self._SM_CYSCREEN)
            w, h = 360, 300
            x, y = (sw - w) // 2, (sh - h) // 2
            self.hwnd = user32.CreateWindowExW(
                self._WS_EX_TOPMOST,
                "JMComicLiteSplash",
                self._title,
                self._WS_POPUP | self._WS_VISIBLE,
                x, y, w, h,
                0, 0, hinst, 0,
            )
            if not self.hwnd:
                self.hwnd = None
                return
            # 若 close() 已先被调用（极端竞态），立即销毁
            if self._close_requested:
                user32.DestroyWindow(self.hwnd)
                return

            msg = ctypes.wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception:
            self.hwnd = None

    def _wndproc(self, hwnd, msg, wparam, lparam):
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        if msg == self._WM_PAINT:
            self._on_paint(hwnd, user32, gdi32)
            return 0
        if msg == self._WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _on_paint(self, hwnd, user32, gdi32):
        ps = self._PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
        rect = self._RECT()
        user32.GetClientRect(hwnd, ctypes.byref(rect))
        try:
            # 背景 #f5f6fa -> COLORREF 0x00BBGGRR = 0x00FAF6F5
            bg = gdi32.CreateSolidBrush(0x00FAF6F5)
            gdi32.FillRect(hdc, ctypes.byref(rect), bg)
            gdi32.DeleteObject(bg)

            cx = (rect.left + rect.right) // 2
            logo_top = rect.top + 44
            # 无边框笔（避免 logo 黑边）
            null_pen = gdi32.GetStockObject(self._NULL_PEN)
            gdi32.SelectObject(hdc, null_pen)
            # 紫色 logo 块 #7B6FE0 -> 0x00E06F7B
            purple = gdi32.CreateSolidBrush(0x00E06F7B)
            gdi32.SelectObject(hdc, purple)
            gdi32.RoundRect(hdc, cx - 44, logo_top, cx + 44, logo_top + 88, 24, 24)
            gdi32.DeleteObject(purple)

            # 文本：标题 + 提示（#5a6478 -> 0x0078645A）
            gdi32.SetBkMode(hdc, self._TRANSPARENT)
            gdi32.SetTextColor(hdc, 0x0078645A)
            tr1 = self._RECT(rect.left, logo_top + 112, rect.right, logo_top + 142)
            gdi32.DrawTextW(
                hdc, self._title, -1, ctypes.byref(tr1),
                self._DT_CENTER | self._DT_SINGLELINE,
            )
            tr2 = self._RECT(rect.left, logo_top + 152, rect.right, logo_top + 178)
            gdi32.DrawTextW(
                hdc, self._hint, -1, ctypes.byref(tr2),
                self._DT_CENTER | self._DT_SINGLELINE,
            )
        finally:
            user32.EndPaint(hwnd, ctypes.byref(ps))

    def close(self):
        """关闭原生预启动窗（WebView2 splash 已就绪后调用，视觉无缝衔接）。"""
        self._close_requested = True
        hwnd = self.hwnd
        if hwnd:
            try:
                ctypes.windll.user32.PostMessageW(hwnd, self._WM_CLOSE, 0, 0)
            except Exception:
                pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)


def wait_for_server(url: str, timeout: float = 10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return
        except Exception:
            time.sleep(0.1)
    raise TimeoutError(f"服务启动超时: {url}")


class FlaskServerThread(threading.Thread):
    def __init__(self, app, host: str, port: int):
        super().__init__(daemon=True)
        self._server = make_server(host, port, app, threaded=True)

    def run(self):
        self._server.serve_forever()

    def shutdown(self):
        self._server.shutdown()


def _log_error(msg: str):
    """启动错误写入用户目录日志，窗口打不开时也能留痕排查。"""
    try:
        base = get_default_user_base_dir()
        base.mkdir(parents=True, exist_ok=True)
        with open(base / "startup_error.log", "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def configure_utf8_output():
    """强制 stdout/stderr 使用 UTF-8。

    Windows 中文系统默认 GBK，jmcomic 打印含特殊字符（如 ♡）的漫画标题 /
    进度信息时会抛 'gbk' codec can't encode character，导致下载流程中断。
    需在 import 业务模块之前调用，确保全局生效。
    """
    if sys.platform != "win32":
        return
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "buffer"):
            continue
        if getattr(stream, "_utf8_forced", False):
            continue
        try:
            new_stream = io.TextIOWrapper(
                stream.buffer,
                encoding="utf-8",
                errors="replace",  # 极少数无法编码的字符用  替代而非崩溃
                newline=None,
                line_buffering=getattr(stream, "line_buffering", False),
            )
            new_stream._utf8_forced = True
            setattr(sys, stream_name, new_stream)
        except Exception:
            pass


def _open_window(url: str, base_dir: Path, boot_backend=None, native_splash=None):
    """splash 先行：窗口立即显示加载动画，后端就绪后同窗口无缝切到主界面。

    回退链：无 pywebview → 同步起后端 + 系统浏览器；后端启动失败 → 窗口显示
    错误提示（并写 startup_error.log，重启不丢线索）。
    """
    try:
        import webview
    except ImportError:
        log.info("未安装 pywebview，回退到浏览器模式。")
        log.info(f"当前数据目录: {base_dir}")
        if boot_backend:
            boot_backend()
        if native_splash is not None:
            try:
                native_splash.close()
            except Exception:
                pass
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return

    window = webview.create_window(
        WINDOW_TITLE,
        html=_SPLASH_HTML,          # 先挂加载动画（内嵌，无外部依赖）
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        min_size=WINDOW_MIN_SIZE,
    )

    # 后端启动与 WebView2 引擎初始化并行：窗口已挂 splash，引擎在 webview.start
    # 内初始化；这段时间同步跑后端 import + 起服务，省掉串行等待。
    _boot_result = {}
    def _run_boot():
        try:
            _boot_result["ok"] = boot_backend() if boot_backend else True
        except Exception as exc:
            _log_error(f"[启动] 后端启动异常: {exc}\n{traceback.format_exc()}")
            _boot_result["ok"] = False
    _boot_thread = threading.Thread(target=_run_boot, daemon=True)
    _boot_thread.start()

    def _on_gui_ready():
        """GUI 就绪后（WebView2 引擎已初始化）：等后端就绪即可切主界面。"""
        t0 = time.time()
        _boot_thread.join()                    # 通常引擎初始化期间已完成
        # 关闭原生预启动窗：WebView2 内嵌 splash 已就绪，视觉无缝衔接
        if native_splash is not None:
            try:
                native_splash.close()
            except Exception:
                pass
        ok = _boot_result.get("ok", False)
        # 最短展示时长：动画不能被「太快」吃掉（渲染在 GUI 线程，此处 sleep 不影响动画播放）
        remain = _SPLASH_MIN_SECONDS - (time.time() - t0)
        if remain > 0:
            time.sleep(remain)
        try:
            if ok:
                window.load_url(url)          # 无缝切主界面
            else:
                window.load_url("data:text/html;charset=utf-8," + urllib.parse.quote(_BOOT_ERROR_HTML))
        except Exception as exc:
            _log_error(f"[启动] 切换主界面失败: {exc}\n{traceback.format_exc()}")

    try:
        # private_mode=False 才能持久化 localStorage；storage_path 指定
        # WebView2 用户数据目录，配合固定端口实现数据持久化。
        webview.start(
            _on_gui_ready,
            debug=False,
            private_mode=False,
            storage_path=str(base_dir / "webview_data"),
        )
    except Exception as exc:
        tb = traceback.format_exc()
        _log_error(f"[回退浏览器] pywebview 启动失败: {exc}\n{tb}")
        log.warning(f"pywebview 启动失败，已回退到浏览器模式: {exc}")
        if native_splash is not None:
            try:
                native_splash.close()
            except Exception:
                pass
        if boot_backend:
            boot_backend()                        # 幂等，确保服务在跑
        log.info(f"请用浏览器打开: {url}")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    finally:
        try:
            window.destroy()
        except Exception:
            pass


def _register_startup_workers():
    """启动后的三项后台工作（临时下载恢复 / 云同步 / 回收站到期清理）。"""
    try:
        import asyncio
        from core.services.download_manager import DownloadManager

        def _startup_recover():
            try:
                asyncio.run(DownloadManager().recover_temp_downloads())
            except Exception as e:
                log.warning(f"启动恢复临时下载失败: {e}")

        threading.Thread(target=_startup_recover, daemon=True).start()
    except Exception as e:
        log.warning(f"注册启动恢复失败: {e}")

    try:
        from core.services.sync_manager import SyncManager

        def _startup_sync():
            try:
                SyncManager().auto_sync_if_due()
            except Exception as e:
                log.warning(f"启动云同步失败: {e}")

        threading.Thread(target=_startup_sync, daemon=True).start()
    except Exception as e:
        log.warning(f"注册启动云同步失败: {e}")

    try:
        from core.services import recycle as recycle_service
        from core.services.comic_manager import ComicManager

        def _startup_recycle_purge():
            try:
                n = recycle_service.purge_expired(ComicManager())
                if n:
                    log.info(f"[Recycle] 启动到期清理完成：{n} 本")
            except Exception as e:
                log.warning(f"启动回收站检查失败: {e}")

        threading.Thread(target=_startup_recycle_purge, daemon=True).start()
    except Exception as e:
        log.warning(f"注册启动回收站检查失败: {e}")


def _preheat_backend():
    """后台预热：重模块已惰性化（启动提速），这里提前加载 + 预构造 crawler/client
    （含域名更新），用户点搜索/下载时零等待。失败静默。"""
    try:
        # 预热重模块（用 importlib 显式调用，避免「import 了但没引用」的静态告警）
        import importlib
        importlib.import_module("jmcomic")
        from core.services.jm_crawler import get_jm_crawler
        get_jm_crawler()._get_client()
    except Exception as e:
        log.warning(f"启动预热失败: {e}")


def run_desktop():
    configure_utf8_output()
    configure_windows_app_id()
    base_dir = configure_runtime_env()

    port = get_or_create_port(base_dir)
    url = f"http://127.0.0.1:{port}"
    state = {"server": None}

    # 原生预启动窗：在 import webview 之前弹出，消除「点开到 splash 出现」的空白期
    splash = NativeSplash()

    def _boot_backend():
        """（幂等）加载后端 + 起服务 + 预热；供 splash 切换与浏览器回退共用。"""
        if state.get("server") is not None:
            return True
        from core.app import app  # 重导入后移到此处：窗口先出现
        _register_startup_workers()
        server = FlaskServerThread(app, "127.0.0.1", port)
        state["server"] = server
        server.start()
        wait_for_server(url)
        threading.Thread(target=_preheat_backend, daemon=True).start()
        return True

    try:
        _open_window(url, base_dir, _boot_backend, splash)
    finally:
        srv = state.get("server")
        if srv is not None:
            try:
                srv.shutdown()
            except Exception:
                pass


if __name__ == "__main__":
    try:
        run_desktop()
    except Exception:
        tb = traceback.format_exc()
        try:
            _log_error("[致命错误] 启动失败:\n" + tb)
        except Exception:
            pass
        log.error(tb)