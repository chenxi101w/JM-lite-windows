# -*- coding: utf-8 -*-
"""页面路由（7 个 SPA 页面壳）。"""

from flask import Blueprint, redirect, render_template

bp = Blueprint("pages", __name__)


@bp.get("/")
def index():
    return redirect("/search")


@bp.get("/search")
def page_search():
    return render_template("search.html", active="search")


@bp.get("/library")
def page_library():
    return render_template("library.html", active="library")


@bp.get("/downloads")
def page_downloads():
    return render_template("downloads.html", active="downloads")


@bp.get("/reader/<int:jm_id>")
def page_reader(jm_id: int):
    return render_template("reader.html", active="reader", jm_id=jm_id)


@bp.get("/settings")
def page_settings():
    return render_template("settings.html", active="settings")


@bp.get("/subscriptions")
def page_subscriptions():
    return render_template("subscriptions.html", active="subscriptions")
