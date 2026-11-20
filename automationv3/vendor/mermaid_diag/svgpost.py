"""One SVG that follows light and dark mode, made from a light render and a dark render of the same diagram.

The two renders differ only in their colours (layout doesn't depend on them), so they are walked side by side and
each colour that differs becomes a CSS variable:

- a colour that is a palette token in both (paper, ink, accent...) becomes ``var(--md-<token>)``, which a page can
  override on the SVG;
- any other becomes a variable of this diagram, ``var(--md-c<n>)``.

The variables are defined in a <style> at the top of the SVG, light by default, dark under
``prefers-color-scheme: dark`` unless the root element has ``<attr>="light"``, and dark whenever it has
``<attr>="dark"``. All of it is in ``:where()``, so it has no specificity and any rule of the page wins.

Colours in CSS (the <style>, style="" attributes) are replaced where they are. A presentation attribute
(fill="#abc") can't hold var(), so it keeps its light colour and a zero-specificity rule for it is added: it beats
the attribute and loses to Mermaid's own rules, exactly as the attribute did.
"""

from __future__ import annotations

import re
from typing import Mapping

from .theme import PALETTES

COLOR = re.compile(
    r"(?<![&\w])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})(?![\w-])"
    r"|\b(?:rgba?|hsla?)\([^()<>\"]*\)"
)

NAMED = {
    "white": "#ffffff", "black": "#000000", "red": "#ff0000", "green": "#008000", "blue": "#0000ff",
    "yellow": "#ffff00", "gray": "#808080", "grey": "#808080", "lightgray": "#d3d3d3", "lightgrey": "#d3d3d3",
    "darkgray": "#a9a9a9", "darkgrey": "#a9a9a9", "silver": "#c0c0c0", "orange": "#ffa500", "purple": "#800080",
    "navy": "#000080", "teal": "#008080", "maroon": "#800000", "olive": "#808000", "aqua": "#00ffff",
    "fuchsia": "#ff00ff", "lime": "#00ff00", "whitesmoke": "#f5f5f5", "gainsboro": "#dcdcdc",
}
_COLOR_PROPS = r"fill|stroke|color|background-color|background|stop-color|flood-color|lighting-color|border-color|outline-color"
_NAMED_IN_CSS = re.compile(r"((?:^|[;{\s\"'])(?:" + _COLOR_PROPS + r")\s*:\s*)(" + "|".join(NAMED) + r")\b", re.I)
_NAMED_IN_ATTR = re.compile(r"(\s(?:fill|stroke|stop-color|flood-color|color)=\")(" + "|".join(NAMED) + r")(\")", re.I)
_ATTR_BEFORE = re.compile(r"\s(fill|stroke|stop-color|flood-color|lighting-color|color)\s*=\s*([\"'])$")
_SVG_OPEN = re.compile(r"<svg\b[^>]*>")


def normalize_named(svg: str) -> str:
    """Named colours in colour properties and attributes as #rrggbb, so both renders spell colours alike."""
    svg = _NAMED_IN_CSS.sub(lambda m: m[1] + NAMED[m[2].lower()], svg)
    return _NAMED_IN_ATTR.sub(lambda m: m[1] + NAMED[m[2].lower()] + m[3], svg)


def _hsl_to_rgb(h: float, s: float, l: float) -> tuple[float, float, float]:
    import colorsys
    return tuple(v * 255 for v in colorsys.hls_to_rgb((h % 360) / 360, l, s))


def _canon(color: str) -> str:
    """One spelling per colour: #rrggbb when opaque (from #rgb, rgb(), hsl() too), #rrggbbaa otherwise."""
    c = color.strip().lower().replace(" ", "")
    if re.fullmatch(r"#[0-9a-f]{3,4}", c):
        c = "#" + "".join(ch * 2 for ch in c[1:])
    m = re.fullmatch(r"(rgba?|hsla?)\(([^)]*)\)", c)
    if m:
        parts = [p for p in re.split(r"[,/]", m[2]) if p]
        try:
            nums = [float(p.rstrip("%deg")) for p in parts]
        except ValueError:
            return c
        if len(nums) < 3:
            return c
        alpha = nums[3] / (100 if parts[3].endswith("%") else 1) if len(nums) > 3 else 1.0
        if m[1].startswith("rgb"):
            rgb = [n * 2.55 if p.endswith("%") else n for n, p in zip(nums[:3], parts[:3])]
        else:
            rgb = list(_hsl_to_rgb(nums[0], nums[1] / 100, nums[2] / 100))
        c = "#" + "".join(f"{max(0, min(255, round(v))):02x}" for v in rgb)
        if alpha < 1:
            c += f"{round(alpha * 255):02x}"
    if re.fullmatch(r"#[0-9a-f]{6}ff", c):
        c = c[:7]
    return c


class Mismatch(ValueError):
    """The two renders differ in more than colour; they can't be merged."""


def merge_themes(light: str, dark: str, svg_id: str, attribute: str = "data-theme",
                 palettes: Mapping[str, Mapping[str, str]] = PALETTES) -> str:
    """The light SVG with every colour that differs in the dark SVG turned into a CSS variable (see module doc)."""
    light, dark = normalize_named(light), normalize_named(dark)
    lp, dp = COLOR.split(light), COLOR.split(dark)
    lc, dc = COLOR.findall(light), COLOR.findall(dark)
    if len(lc) != len(dc) or lp != dp:
        raise Mismatch("the light and dark renders differ in more than their colours")

    tokens = {}
    for name, value in palettes["light"].items():
        tokens.setdefault((_canon(value), _canon(palettes["dark"][name])), name)

    used_tokens: set[str] = set()
    own: dict[tuple[str, str], str] = {}

    def var_for(cl: str, cd: str) -> str:
        key = (_canon(cl), _canon(cd))
        token = tokens.get(key)
        if token:
            used_tokens.add(token)
            return f"--md-{token}"
        if key not in own:
            own[key] = f"--md-c{len(own)}"
        return own[key]

    attr_rules: dict[tuple[str, str], str] = {}   # (attribute, light value) -> variable
    conflicts: list[tuple[str, int, str]] = []    # per-element rules where one light value has two dark ones
    out = [lp[0]]
    marks: dict[int, str] = {}                    # index into `out` -> marker attribute to insert before it
    for i, (cl, cd) in enumerate(zip(lc, dc)):
        before = lp[i]
        if _canon(cl) == _canon(cd):
            out.append(cl)
            out.append(lp[i + 1])
            continue
        var = var_for(cl, cd)
        attr = _ATTR_BEFORE.search(before)
        if attr and lp[i + 1].startswith(attr[2]):
            key = (attr[1], cl)
            if attr_rules.setdefault(key, var) != var:
                n = len(conflicts)
                conflicts.append((attr[1], n, var))
                marks[len(out) - 1] = f' data-md-{attr[1]}="{n}"'
            out.append(cl)
        else:
            out.append(f"var({var})")
        out.append(lp[i + 1])
    for index, mark in marks.items():
        text = out[index]
        m = _ATTR_BEFORE.search(text)
        out[index] = text[:m.start()] + mark + text[m.start():]
    svg = "".join(out)

    sel = f"#{svg_id}"
    light_decls, dark_decls = [], []
    for token in sorted(used_tokens):
        light_decls.append(f"--md-{token}:{palettes['light'][token]}")
        dark_decls.append(f"--md-{token}:{palettes['dark'][token]}")
    for (cl, cd), name in own.items():
        light_decls.append(f"{name}:{cl}")
        dark_decls.append(f"{name}:{cd}")
    css = []
    if light_decls:
        css.append(f":where({sel}){{{';'.join(light_decls)}}}")
        css.append(f'@media (prefers-color-scheme:dark){{:where(:root:not([{attribute}="light"]) {sel}){{{";".join(dark_decls)}}}}}')
        css.append(f':where(:root[{attribute}="dark"] {sel}){{{";".join(dark_decls)}}}')
    for (prop, value), var in attr_rules.items():
        css.append(f':where({sel} [{prop}="{value}"]){{{prop}:var({var})}}')
    for prop, n, var in conflicts:
        css.append(f':where({sel} [data-md-{prop}="{n}"]){{{prop}:var({var})}}')
    if not css:
        return svg
    head = _SVG_OPEN.search(svg)
    return svg[:head.end()] + "<style>" + "".join(css) + "</style>" + svg[head.end():]
