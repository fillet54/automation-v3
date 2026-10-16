"""The built documentation, served as a part of the site

The docs theme (docs/_themes/automation) marks the regions of each page that
are the site's shell: <!--ui:head-->…<!--/ui:head--> (the fonts), <!--ui:top-->
…<!--/ui:top--> (the body tag, markings and header) and <!--ui:bottom-->
…<!--/ui:bottom-->. Serving a page fills them from templates/docs_shell.html,
so the docs carry this server's brand, nav, markings, fonts and theme. A page
without the marks (another theme, or no theme) is served as it is.
"""

import re
from pathlib import Path

from flask import abort, current_app, render_template, send_from_directory
from markupsafe import escape
from werkzeug.security import safe_join

REGIONS = ("head", "top", "bottom")


def serve(filename):
    """A file of the docs build: an HTML page in the site's shell, anything else as it is"""
    root = current_app.config.get("DOCS_PATH")
    if not root:
        abort(404)
    if not filename.endswith(".html"):
        return send_from_directory(root, filename)
    path = safe_join(str(root), filename)
    if path is None or not Path(path).is_file():
        abort(404)
    return in_shell(Path(path).read_text(encoding="utf-8"))


def in_shell(page):
    """`page` (HTML) with its marked regions filled with the site's shell"""
    for region in REGIONS:
        pattern = re.compile(rf"<!--ui:{region}-->.*?<!--/ui:{region}-->", re.DOTALL)
        shell = render_template("docs_shell.html", region=region)
        page = pattern.sub(lambda _: shell, page, count=1)
    config = current_app.config
    if config["UI_THEME"] in ("light", "dark"):
        page = page.replace("<html", f'<html data-ui-theme="{config["UI_THEME"]}"', 1)
    if config["UI_MARKING"]:
        page = page.replace("</title>", f' · {escape(config["UI_MARKING"]["text"])}</title>', 1)
    return page
