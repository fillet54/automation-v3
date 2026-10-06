"""Support for the UI components (templates/ui/, static/css/ui.css): config, filters and shell context.

The components are cmtrack's UI library (the cmstatus project), so the tools look alike.

Config (create_app(**config), or the environment at startup):
    UI_BRAND        the wordmark in the header and the default page title (AUTOMATION_UI_BRAND).
    UI_MARKING      {"text", "bg", "fg"} for top/bottom marking banners, from AUTOMATION_MARKING
                    (UNCLASSIFIED and CUI have standard colours; anything else also needs
                    AUTOMATION_MARKING_COLORS="#bg,#fg"). Unset: no banners.
    UI_THEME        auto (follow the system, the default) | light | dark (AUTOMATION_UI_THEME).
    UI_FONTS_CSS    stylesheet that loads Source Serif 4, Inter and IBM Plex Mono (AUTOMATION_UI_FONTS_CSS).
                    Defaults to Google Fonts; point it at self-hosted fonts on a closed network, or "" for
                    the system fallbacks named in ui.css.
"""

import datetime as dt
import os

from flask import current_app, url_for

MARKING_COLORS = {"UNCLASSIFIED": ("#007A33", "#FFFFFF"), "CUI": ("#502B85", "#FFFFFF")}

GOOGLE_FONTS = (
    "https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600"
    "&family=Inter:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,500&display=swap"
)
THEMES = ("auto", "light", "dark")

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
    text = (text if text is not None else os.environ.get("AUTOMATION_MARKING", "")).strip()
    if not text:
        return None
    colors = colors if colors is not None else os.environ.get("AUTOMATION_MARKING_COLORS", "")
    if colors:
        bg, _, fg = colors.partition(",")
    elif text.upper() in MARKING_COLORS:
        bg, fg = MARKING_COLORS[text.upper()]
    else:
        raise ValueError(
            f'marking {text!r} has no standard colours; set AUTOMATION_MARKING_COLORS="#bg,#fg"')
    return {"text": text, "bg": bg.strip(), "fg": (fg or "#FFFFFF").strip()}


def _as_utc(value):
    """datetime (aware = converted, naive = assumed UTC, as SQLite's CURRENT_TIMESTAMP is) or None."""
    if isinstance(value, dt.datetime):
        d = value
    elif isinstance(value, str) and len(value) > 10:
        try:
            d = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00").replace(" ", "T", 1))
        except ValueError:
            return None
    else:
        return None
    return d.replace(tzinfo=dt.timezone.utc) if d.tzinfo is None else d.astimezone(dt.timezone.utc)


def utc(value, seconds=False):
    """'2026-09-23 14:24Z'. Anything unreadable is shown as it is; empty stays empty."""
    if not value:
        return ""
    d = _as_utc(value)
    if d is None:
        return str(value)
    return d.strftime("%Y-%m-%d %H:%M:%SZ" if seconds else "%Y-%m-%d %H:%MZ")


def iso(value):
    """Machine-readable form for <time datetime>."""
    d = _as_utc(value)
    return d.strftime("%Y-%m-%dT%H:%M:%SZ") if d else (str(value) if value else "")


def _nav():
    return [{"key": key, "label": label, "href": url_for(endpoint)} for key, label, endpoint in NAV]


def init_app(app):
    app.config.setdefault("UI_BRAND", os.environ.get("AUTOMATION_UI_BRAND") or "automation")
    app.config.setdefault("UI_MARKING", marking_from_env())
    app.config.setdefault("UI_THEME", os.environ.get("AUTOMATION_UI_THEME") or "auto")
    if app.config["UI_THEME"] not in THEMES:
        raise ValueError(f"UI_THEME must be one of {', '.join(THEMES)}, not {app.config['UI_THEME']!r}")
    app.config.setdefault("UI_FONTS_CSS", os.environ.get("AUTOMATION_UI_FONTS_CSS", GOOGLE_FONTS))
    app.jinja_env.filters["utc"] = utc
    app.jinja_env.filters["iso"] = iso

    @app.context_processor
    def ui_shell():
        c = current_app.config
        return {"ui_brand": c["UI_BRAND"], "ui_marking": c["UI_MARKING"], "ui_theme": c["UI_THEME"],
                "ui_fonts_css": c["UI_FONTS_CSS"], "ui_nav": _nav}
