# -*- coding: utf-8 -*-
"""统一日志 —— 替代散落各处的裸 print。

打包后（windowed exe）stdout 不可见，print 等于把信息丢掉；这里统一收口：
控制台 + 滚动文件（UserData/logs/app.log），真机排查看文件即可。
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

_ROOT = "jmcomic"
_configured = False


def _console_handler() -> logging.Handler:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname).1s %(name)s: %(message)s", "%m-%d %H:%M:%S"))
    return h


def _file_handler(log_dir: str) -> logging.Handler | None:
    try:
        os.makedirs(log_dir, exist_ok=True)
        h = RotatingFileHandler(
            os.path.join(log_dir, "app.log"),
            maxBytes=2 * 1024 * 1024, backupCount=2, encoding="utf-8")
        h.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
        return h
    except OSError:
        return None


def setup(log_dir: str | None = None, level: int = logging.INFO) -> logging.Logger:
    """装配根 logger。重复调用只补文件输出，不重复加控制台 handler。"""
    global _configured
    logger = logging.getLogger(_ROOT)
    logger.setLevel(level)
    if not _configured:
        logger.addHandler(_console_handler())
        _configured = True
    if log_dir and not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
        fh = _file_handler(log_dir)
        if fh is not None:
            logger.addHandler(fh)
    logger.propagate = False
    return logger


def get_logger(name: str = "core") -> logging.Logger:
    """取子 logger；未显式 setup 时也能用（只走控制台）。"""
    if not _configured:
        setup()
    return logging.getLogger(f"{_ROOT}.{name}")
