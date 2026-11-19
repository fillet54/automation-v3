"""paper-ui's Sphinx theme, "paper"

    html_theme = "paper"
    html_theme_options = {"brand": "automation"}

Installing paper-ui registers the theme (an entry point), so that is all conf.py needs. The build gets paper-ui's
static files in _static: ui.css (which docs.css builds on), code.css, fonts.css and the IBM Plex fonts, so the
docs look like the tools and work offline. Options (theme.toml): brand, nav_label, home_label,
globaltoc_maxdepth, line_breaks, layout, layouts, margin, sidenotes.

``layout`` is how the documents are laid out (ui.css: narrow, medium, full, tufte) and ``layouts`` the ones a
reader may choose instead, in the side column (layout.js remembers the choice). The tufte layout has a margin:
``margin`` says what goes in it (sidebars, version notes, notes...) and ``sidenotes`` whether footnotes appear
there beside their references (paper_ui.margins, which also gives the docs ``.. margin::``, ``:sidenote:`` and
``:marginnote:``, and the classes ``ui-margin`` and ``ui-wide`` for any directive's ``:class:``).

``line_breaks = "live"`` sets the paragraphs' lines as TeX would, worked out in the reader's browser
(linebreak-live.js, with hyph-en-us.js for hyphens) at whatever width they are; "browser" (the default)
leaves them to the browser.

Pages depend on the stylesheets, so editing paper-ui's CSS rebuilds them rather than leaving them up to date.
"""

from pathlib import Path

from sphinx.util import logging

from .. import STATIC, __version__, margins

logger = logging.getLogger(__name__)

THEME = Path(__file__).resolve().parent / "paper"
STYLESHEETS = [THEME / "static" / "docs.css", STATIC / "ui.css", STATIC / "fonts.css"]
LAYOUTS = {"narrow": "Narrow", "medium": "Medium", "full": "Full width", "tufte": "Tufte"}
# what each is, in the header's settings menu (layout.js)
LAYOUT_NOTES = {"narrow": "Short lines; figures and tables wider",
                "medium": "Longer lines; figures and tables wider",
                "full": "Text as wide as figures and tables",
                "tufte": "Notes in a margin beside the text"}


def layouts(options):
    """[(layout, label)] a reader may choose from (the docs' own among them) and the docs' own: from the
    theme's options (theme_layout, theme_layouts)"""
    default = (options.get("theme_layout") or "medium").strip()
    if default not in LAYOUTS:
        raise ValueError(f"paper theme: layout {default!r} is not one of {', '.join(LAYOUTS)}")
    offered = [v.strip() for v in str(options.get("theme_layouts") or "").replace(",", " ").split()]
    unknown = [v for v in offered if v not in LAYOUTS]
    if unknown:
        raise ValueError(f"paper theme: layouts {', '.join(unknown)} not among {', '.join(LAYOUTS)}")
    names = [v for v in LAYOUTS if v in offered or v == default]      # narrowest first, as the menu lists them
    return [(v, LAYOUTS[v]) for v in names], default


def paper_options(app):
    """The paper theme's options (theme_*) when this is an HTML build with it, else None"""
    context = getattr(app.builder, "globalcontext", None) or {}
    return context if "theme_layouts" in context else None


def set_margins(app, doctree, docname):
    """The tufte layout's sidenotes and margin notes (paper_ui.margins), in every page: the reader chooses"""
    options = paper_options(app)
    if options is None:
        return
    margins.apply(doctree, margin=options.get("theme_margin"),
                  sidenotes=str(options.get("theme_sidenotes", "true")).lower() not in ("false", "no", "0", ""))


def set_layout(app, pagename, templatename, context, doctree):
    if paper_options(app) is not None:
        context["paper_layouts"], context["paper_layout"] = layouts(context)
        context["paper_layout_notes"] = LAYOUT_NOTES


def add_static(app):
    """paper-ui's static folder before the project's own, so a project file of the same name wins"""
    theme = getattr(app.builder, "theme", None)
    # theme._dirs: the theme's folder and those of the themes it inherits from (a project theme can extend paper)
    if theme is None or THEME not in [Path(d).resolve() for d in getattr(theme, "_dirs", ())]:
        return
    if str(STATIC) not in map(str, app.config.html_static_path):
        app.config.html_static_path = [str(STATIC), *app.config.html_static_path]


def depend_on_stylesheets(app, docname, source):
    for stylesheet in STYLESHEETS:
        app.env.note_dependency(str(stylesheet))


LINE_BREAKS = ("browser", "live")


def check_line_breaks(app, pagename, templatename, context, doctree):
    """Say once if line_breaks is something the theme doesn't know (as "tex", from before it was live)"""
    value = context.get("theme_line_breaks")
    if value not in LINE_BREAKS and not getattr(app, "_paper_line_breaks_warned", False):
        app._paper_line_breaks_warned = True
        logger.warning('paper theme: line_breaks = %r: it is "live" (TeX line breaks in the browser) or '
                       '"browser"; the browser breaks the lines', value)


def setup(app):
    app.add_html_theme("paper", str(THEME))
    app.add_directive("margin", margins.Margin)
    app.add_role("sidenote", margins.sidenote_role)
    app.add_role("marginnote", margins.marginnote_role)
    app.connect("doctree-resolved", set_margins)
    app.connect("html-page-context", set_layout)
    app.connect("builder-inited", add_static)
    app.connect("source-read", depend_on_stylesheets)
    app.connect("html-page-context", check_line_breaks)
    return {"version": __version__, "parallel_read_safe": True, "parallel_write_safe": True}
