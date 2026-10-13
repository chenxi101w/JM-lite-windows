# -*- coding: utf-8 -*-
"""蓝图注册入口。

在函数内部 import 各蓝图，避免 core.web 包初始化时形成环形依赖
（蓝图模块都要 from core.web.common import ...）。
"""


def register_blueprints(app) -> None:
    from core.web import (
        downloads,
        library,
        pages,
        reader,
        search,
        subscriptions,
        system,
    )
    for module in (pages, system, search, downloads, reader, library, subscriptions):
        app.register_blueprint(module.bp)
