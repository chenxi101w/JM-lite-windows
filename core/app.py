# -*- coding: utf-8 -*-
"""Flask 应用工厂 —— 装配层。

原 1500 行单文件应用已拆解为：本文件（装配）+ `core/web/*`（按业务域划分的蓝图）。
对外仍暴露模块级 `app`，`desktop_app.py` 的 `from core.app import app` 用法不变。
"""

import os

from flask import Flask

from core.config import (APP_VERSION, BASE_DIR, STATIC_DIR, TEMPLATE_DIR,
                         load_app_version)
from core.logging_setup import setup
from core.models.database import init_database
from core.services import subscription as sub_service
from core.services.filter_service import ensure_aliases_seeded
from core.services.jm_crawler import get_jm_crawler
from core.web import register_blueprints


def create_app() -> Flask:
    load_app_version()
    setup(os.path.join(BASE_DIR, "logs"))

    app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
    app.json.ensure_ascii = False

    init_database()
    ensure_aliases_seeded()

    @app.context_processor
    def inject_globals():
        return {"app_version": APP_VERSION, "app_name": "JM 轻量版"}

    register_blueprints(app)

    # 订阅自动巡检（启动后延迟 3 分钟首检，此后每小时一次；daemon 线程）
    sub_service.schedule(get_jm_crawler)
    return app


app = create_app()
