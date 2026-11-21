"""The web UI's look: paper-ui (the engineering tools' shared UI library, vendored in automationv3/vendor), set up for this app.

paper-ui supplies the stylesheet, components (templates/ui/components.html), page shell, filters and the
bundled IBM Plex fonts; this app adds its own pieces on top (static/css/automation.css, templates/ui/outcomes.html).

Config (create_app(**config), or the environment at startup):
    UI_BRAND        the wordmark in the header and the default page title (AUTOMATION_UI_BRAND).
    UI_MARKING      {"text", "bg", "fg"} for top/bottom marking banners, from AUTOMATION_MARKING
                    (UNCLASSIFIED and CUI have standard colours; anything else also needs
                    AUTOMATION_MARKING_COLORS="#bg,#fg"). Unset: no banners.
    UI_THEME        auto (follow the system, the default) | light | dark (AUTOMATION_UI_THEME).
"""

import os

from .. import documents as documents_pkg
from ..documents.html import requirement_html
from ..vendor import paper_ui
from ..vendor.paper_ui import flask as paper_ui_flask
from flask import current_app, send_from_directory, url_for
from ..vendor.paper_ui import iso, utc  # noqa: F401  (the filters, as they were here)

MARKING_COLORS = paper_ui.MARKING_COLORS
THEMES = paper_ui.THEMES

# (key, label, endpoint) for the header nav
NAV = [
    ("workspace", "Workspace", "index"),
    ("requirements", "Requirements", "requirements.list"),
    ("queue", "Queue", "jobqueue.list"),
    ("reports", "Reports", "reports.index"),
    ("scratch", "Scratch", "scratch.index"),
    ("workers", "Workers", "jobqueue.list_workers"),
]


def marking_from_env(text=None, colors=None):
    """Banner config from AUTOMATION_MARKING / AUTOMATION_MARKING_COLORS; None when not set."""
    text = text if text is not None else os.environ.get("AUTOMATION_MARKING", "")
    colors = colors if colors is not None else os.environ.get("AUTOMATION_MARKING_COLORS", "")
    try:
        return paper_ui.marking(text, colors)
    except ValueError:
        raise ValueError(
            f'marking {text.strip()!r} has no standard colours; set AUTOMATION_MARKING_COLORS="#bg,#fg"') from None


def _nav():
    from .auth import central, current_user, is_admin
    if central() and current_user() is None:
        return []  # signing in: nowhere else to go yet
    from .client_mode import CENTRAL_NAV, central as central_server, central_url
    items = [{"key": key, "label": label,
              "href": central_url(CENTRAL_NAV[key]) if central_server() and key in CENTRAL_NAV
              else url_for(endpoint)}
             for key, label, endpoint in NAV]
    if current_app.config.get("DOCS_PATH"):
        items.append({"key": "docs", "label": "Docs", "href": url_for("docs")})
    if central():
        items.append({"key": "account", "label": "Account", "href": url_for("auth.account")})
    if is_admin():
        items.append({"key": "admin", "label": "Admin", "href": url_for("auth.admin")})
    return items


def init_app(app):
    app.config.setdefault("UI_BRAND", os.environ.get("AUTOMATION_UI_BRAND") or "automation")
    app.config.setdefault("UI_MARKING", marking_from_env())
    app.config.setdefault("UI_THEME", os.environ.get("AUTOMATION_UI_THEME") or "auto")
    paper_ui_flask.init_app(app, home=lambda: url_for("index"), nav=_nav)
    app.jinja_env.filters["requirement_html"] = requirement_html

    @app.route("/static/css/automation.css")
    def automation_css():
        return send_from_directory(documents_pkg.STATIC, "automation.css")
