"""paper-ui in a Flask app

    from paper_ui.flask import init_app
    init_app(app, nav=[{"key": "runs", "label": "Runs", "href": "/runs"}])

serves paper-ui's static files at /paper-ui/static (``url_for("paper_ui.static", filename="ui.css")``, or
``ui_static("ui.css")`` in a template), puts its templates behind the app's own (``ui/components.html``,
``ui/layout.html``) and gives every template the shell's context and the ``utc`` and ``iso`` filters.

Config (set before init_app, or passed to it; the app's settings win):
    UI_BRAND        the wordmark in the header and the default page title.
    UI_MARKING      {"text", "bg", "fg"} for top/bottom marking banners (paper_ui.marking makes one); None: no banners.
    UI_THEME        auto (follow the system, the default) | light | dark.
    UI_HOME         where the wordmark links to (default "/").
    UI_NAV          the header's nav: [{"key", "label", "href"}].
UI_HOME and UI_NAV can be functions instead, called for each page (so they can use url_for).
"""

from flask import Blueprint, url_for

from . import STATIC, TEMPLATES, THEMES, iso, utc

URL_PREFIX = "/paper-ui"


def init_app(app, brand=None, marking=None, theme=None, home=None, nav=None, url_prefix=URL_PREFIX):
    given = {"UI_BRAND": brand, "UI_MARKING": marking, "UI_THEME": theme, "UI_HOME": home, "UI_NAV": nav}
    defaults = {"UI_BRAND": "", "UI_MARKING": None, "UI_THEME": "auto", "UI_HOME": "/", "UI_NAV": ()}
    for key, value in given.items():
        app.config.setdefault(key, defaults[key] if value is None else value)
    if app.config["UI_THEME"] not in THEMES:
        raise ValueError(f"UI_THEME must be one of {', '.join(THEMES)}, not {app.config['UI_THEME']!r}")

    app.register_blueprint(Blueprint("paper_ui", __name__, static_folder=str(STATIC),
                                     template_folder=str(TEMPLATES), url_prefix=url_prefix))
    app.jinja_env.filters["utc"] = utc
    app.jinja_env.filters["iso"] = iso

    @app.context_processor
    def ui_shell():
        c = app.config
        return {"ui_brand": c["UI_BRAND"], "ui_marking": c["UI_MARKING"], "ui_theme": c["UI_THEME"],
                "ui_home": _value(c["UI_HOME"]), "ui_nav": _value(c["UI_NAV"]), "ui_static": ui_static}


def _value(setting):
    return setting() if callable(setting) else setting


def ui_static(filename):
    """The URL of one of paper-ui's static files"""
    return url_for("paper_ui.static", filename=filename)
