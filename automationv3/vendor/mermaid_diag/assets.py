"""The CSS and fonts a page with diagrams needs: @font-face rules for the IBM Plex faces and the figure styles."""

from __future__ import annotations

import base64
import json
import shutil
from functools import lru_cache
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
FONTS = PACKAGE / "fonts"
STATIC = PACKAGE / "static"
FAMILY = {"sans": "IBM Plex Sans", "mono": "IBM Plex Mono", "serif": "IBM Plex Serif"}


@lru_cache(maxsize=1)
def faces() -> list[dict]:
    data = json.loads((FONTS / "fonts.json").read_text(encoding="utf-8"))
    return [
        {"family": FAMILY[f["family"]], "weight": f["weight"], "style": "italic" if f["italic"] else "normal",
         "file": f["file"] + ".woff2"}
        for f in data["faces"].values()
    ]


def font_face_css(url_prefix: str | None = None) -> str:
    """@font-face rules for the bundled faces: their woff2 files under `url_prefix` (e.g. "_static/mermaid-diag/"),
    or embedded as data: URIs when it is None (a page that stands alone)."""
    rules = []
    for f in faces():
        if url_prefix is None:
            data = base64.b64encode((FONTS / f["file"]).read_bytes()).decode()
            src = f"url(data:font/woff2;base64,{data})"
        else:
            src = f'url("{url_prefix}{f["file"]}")'
        rules.append(
            f'@font-face{{font-family:"{f["family"]}";font-style:{f["style"]};font-weight:{f["weight"]};'
            f'font-display:block;src:{src} format("woff2")}}'
        )
    return "\n".join(rules)


def figure_css() -> str:
    return (STATIC / "mermaid-diag.css").read_text(encoding="utf-8")


def page_css(url_prefix: str | None = None) -> str:
    """Everything a page needs, in one stylesheet."""
    return font_face_css(url_prefix) + "\n" + figure_css()


def copy_static(dest: Path) -> None:
    """mermaid-diag.css (with @font-face rules pointing next to it) and the woff2 files, into `dest`."""
    dest.mkdir(parents=True, exist_ok=True)
    for f in faces():
        shutil.copyfile(FONTS / f["file"], dest / f["file"])
    shutil.copyfile(FONTS / "OFL.txt", dest / "OFL.txt")
    (dest / "mermaid-diag.css").write_text(page_css(""), encoding="utf-8")


_TITLE_CLASSES = ("flowchartTitleText", "titleText", "pieTitleText", "chart-title", "journey-title", "c4-title",
                  "packetTitle", "radarTitle", "treemapTitle", "quadrant-title", "timeline-title", 'class="title"',
                  "ls-title", "sm-title")


def embed_fonts(svg: str) -> str:
    """The SVG with the fonts it uses embedded (svg_font_css), so it looks the same on its own as in a page."""
    css = svg_font_css(svg)
    if not css:
        return svg
    i = svg.index(">", svg.index("<svg")) + 1
    return svg[:i] + f"<style>{css}</style>" + svg[i:]


def svg_font_css(svg: str) -> str:
    """@font-face rules (embedded) for the faces a standalone SVG is likely to use: Plex Sans always, its other
    weights and italic when the SVG asks for them, Mono when it has code, Serif when it has a title."""
    body = svg.split("</style>")[-1] if "</style>" in svg else svg
    lowered = svg.lower()
    wanted = {("IBM Plex Sans", 400, "normal")}
    for weight, marks in ((500, ("font-weight:500", "font-weight: 500", 'font-weight="500"')),
                          (600, ("font-weight:600", "font-weight: 600", 'font-weight="600"')),
                          (700, ("font-weight:bold", "font-weight: bold", "font-weight:700", "font-weight: 700",
                                 "<b>", "<strong>", 'font-weight="bold"'))):
        if any(m in lowered for m in marks):
            wanted.add(("IBM Plex Sans", weight, "normal"))
    if "<em>" in body or "<i>" in body or "font-style:italic" in lowered:
        wanted.add(("IBM Plex Sans", 400, "italic"))
    if any(f"<{t}" in body for t in ("code", "kbd", "samp")) or "IBM Plex Mono" in body:
        wanted |= {("IBM Plex Mono", 400, "normal"), ("IBM Plex Mono", 600, "normal")}
    if any(c in body for c in _TITLE_CLASSES):
        wanted |= {("IBM Plex Serif", 400, "normal"), ("IBM Plex Serif", 600, "normal")}
    rules = []
    for f in faces():
        if (f["family"], f["weight"], f["style"]) in wanted:
            data = base64.b64encode((FONTS / f["file"]).read_bytes()).decode()
            rules.append(f'@font-face{{font-family:"{f["family"]}";font-style:{f["style"]};font-weight:{f["weight"]};'
                         f'src:url(data:font/woff2;base64,{data}) format("woff2")}}')
    return "".join(rules)
