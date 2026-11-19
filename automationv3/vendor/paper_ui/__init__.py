"""paper-ui: the engineering tools' shared look

One stylesheet (static/ui.css: tokens, shell and components), its Jinja macros (templates/ui/components.html),
a page shell (templates/ui/layout.html), code highlighting (static/code.css) and IBM Plex Sans, Serif and Mono
(static/fonts.css, static/fonts/), plus the glue to use them:

- Flask: ``paper_ui.flask.init_app(app)`` serves the static files and templates and adds the shell's context
  and the ``utc``/``iso`` filters.
- Sphinx: ``html_theme = "paper"`` (paper_ui.sphinx), the same look for documentation.

This module has no dependencies; the helpers here are shared by both.
"""

import datetime as dt
from pathlib import Path

__version__ = "0.1.0"

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
TEMPLATES = HERE / "templates"
FONTS = STATIC / "fonts"

# Standard colours for the common markings; anything else needs its colours given
MARKING_COLORS = {"UNCLASSIFIED": ("#007A33", "#FFFFFF"), "CUI": ("#502B85", "#FFFFFF")}
THEMES = ("auto", "light", "dark")


def marking(text, colors=""):
    """Banner config ({"text", "bg", "fg"}) for a marking, or None for none.

    `colors` is "#bg,#fg"; without it, UNCLASSIFIED and CUI get their standard colours and anything else is
    an error, so a banner is never shown in a made-up colour."""
    text = (text or "").strip()
    if not text:
        return None
    if colors:
        bg, _, fg = colors.partition(",")
    elif text.upper() in MARKING_COLORS:
        bg, fg = MARKING_COLORS[text.upper()]
    else:
        raise ValueError(f'marking {text!r} has no standard colours; give its colours as "#bg,#fg"')
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
