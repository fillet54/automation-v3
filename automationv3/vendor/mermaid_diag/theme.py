"""The look of mermaid-diag's diagrams: palette, fonts, and the Mermaid config made from them.

A diagram is rendered once in the light palette and once in the dark one (see svgpost.py, which turns the two into
one SVG whose colours are CSS variables). Everything here is in literal colours: Mermaid computes with colours
(darkening, mixing), so it can't be handed var()s.

Palette tokens (``--md-paper``, ``--md-ink``, ``--md-accent``...) are the ones from paper-ui's ui.css; a page
can override any of them on the SVG (``.mermaid-diag svg { --md-paper: ... }``).

Tones: a node can take one of the palette's tones as a class, ``A[Server]:::accent``: accent, success, danger,
warning, info, review, and ghost for something outside the system (dashed). layered-software's partitions, layers,
components and bars take them the same way.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Mapping

FONT_SANS = '"IBM Plex Sans", "Helvetica Neue", Arial, sans-serif'
FONT_MONO = '"IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace'
FONT_SERIF = '"IBM Plex Serif", Georgia, "Times New Roman", serif'
FONT_SIZE = 14

TONES = ("accent", "success", "danger", "warning", "info", "review", "verify")

LIGHT = {
    "paper": "#fffefa",
    "soft": "#f4f3ed",
    "ink": "#252c2a",
    "muted": "#5b655e",
    "faint": "#8c948e",
    "rule": "#dedfd8",
    "rule-strong": "#c6c8bf",
    "accent": "#285f51",
    "success": "#306844",
    "danger": "#a03630",
    "warning": "#805b10",
    "info": "#285e97",
    "review": "#795297",
    "verify": "#337272",
}

DARK = {
    "paper": "#181c19",
    "soft": "#222923",
    "ink": "#e6e9e6",
    "muted": "#c7cec9",
    "faint": "#89918b",
    "rule": "#39423b",
    "rule-strong": "#4d584f",
    "accent": "#b7d7c8",
    "success": "#aed5bc",
    "danger": "#f5c0ba",
    "warning": "#e2ca8a",
    "info": "#b4cef3",
    "review": "#d8c4ec",
    "verify": "#a4d6d3",
}


def mix(a: str, b: str, amount: float) -> str:
    """`amount` of colour a, the rest b (both #rrggbb)."""
    x = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    y = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(p * amount + q * (1 - amount)):02x}" for p, q in zip(x, y))


def palette(base: Mapping[str, str]) -> dict[str, str]:
    """The base tokens plus the ones derived from them (tone fills, cluster and note backgrounds)."""
    t = dict(base)
    for tone in TONES:
        t[f"{tone}-bg"] = mix(t[tone], t["paper"], 0.1)
        t[f"{tone}-mid"] = mix(t[tone], t["paper"], 0.28)
    t["cluster-bg"] = mix(t["soft"], t["paper"], 0.6)
    t["note-bg"] = mix(t["info"], t["paper"], 0.07)
    t["note-border"] = mix(t["info"], t["paper"], 0.45)
    return t


PALETTES = {"light": palette(LIGHT), "dark": palette(DARK)}


_IS = re.compile(r":is\(([^()]*)\)")


def expand_is(css: str) -> str:
    """Selector lists without :is(), which novasvg (PNG and PDF) doesn't know: `a > :is(b, c)` -> `a > b, a > c`."""
    out = []
    for rule in re.split(r"(?<=\})", css):
        if "{" not in rule:
            out.append(rule)
            continue
        head, body = rule.split("{", 1)
        selectors = []
        for sel in _top_level(head):
            pending = [sel] if ":is(" not in sel else None
            if pending is None:
                pending = [sel]
                while any(":is(" in x for x in pending):
                    nxt = []
                    for x in pending:
                        m = _IS.search(x)
                        if not m:
                            nxt.append(x)
                            continue
                        nxt += [x[:m.start()] + alt.strip() + x[m.end():] for alt in m[1].split(",")]
                    pending = nxt
            selectors += pending
        out.append(", ".join(x.strip() for x in selectors if x.strip()) + " {" + body)
    return "".join(out)


def _top_level(head: str) -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in head:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


def theme_css(t: Mapping[str, str]) -> str:
    """Mermaid's themeCSS: the shapes, lines and type of the look, in the palette `t`."""
    return expand_is(_theme_css(t))


def _theme_css(t: Mapping[str, str]) -> str:
    tones = "".join(
        f"""
      .node.{tone} > :is(rect, polygon, circle, ellipse, path), .node.{tone} > g > :is(rect, path) {{
        fill: {t[tone + '-bg']} !important; stroke: {t[tone]} !important; }}
      .node.{tone} .nodeLabel, .node.{tone} .nodeLabel p {{ color: {t['ink']} !important; }}"""
        for tone in TONES
    )
    # layered-software (js/layered_software.js): a tone on a partition, layer, component or bar colours its box.
    ls_tones = "".join(
        f"""
      .ls-diagram .{tone} > :is(rect, a > rect) {{ fill: {t[tone + '-bg']} !important; stroke: {t[tone]} !important; }}"""
        for tone in TONES
    )
    # state-machine (js/state_machine.js): a tone on a state colours its box.
    sm_tones = "".join(
        f"""
      .sm-diagram .{tone} > :is(.sm-box, a > .sm-box) {{ fill: {t[tone + '-bg']} !important; stroke: {t[tone]} !important; }}"""
        for tone in TONES
    )
    return f"""
      .node > :is(rect, polygon, circle, ellipse, path), .node > g > :is(rect, path) {{ stroke-width: 1px; }}
      .node > rect, .node > g > rect {{ rx: 3px; ry: 3px; }}
      .node .nodeLabel, .node .nodeLabel p {{ line-height: 1.35; }}
      .node.ghost > :is(rect, polygon, path), .node.ghost > g > :is(rect, path) {{
        fill: {t['paper']} !important; stroke: {t['faint']} !important; stroke-dasharray: 4 3; }}
      .node.ghost .nodeLabel, .node.ghost .nodeLabel p {{ color: {t['muted']} !important; }}
      {tones}
      {ls_tones}
      .ls-diagram .ghost > :is(rect, a > rect) {{ fill: {t['paper']} !important; stroke: {t['faint']} !important; stroke-dasharray: 4 3; }}
      {sm_tones}
      .sm-diagram .ghost > :is(.sm-box, a > .sm-box) {{ fill: {t['paper']} !important; stroke: {t['faint']} !important; stroke-dasharray: 4 3; }}
      .sm-diagram .ghost :is(.sm-name, .sm-code) {{ fill: {t['muted']} !important; }}
      .sm-line.any {{ stroke: {t['danger']} !important; }}
      .sm-arrow.any, .sm-guard.any {{ fill: {t['danger']} !important; }}
      .ls-diagram .ghost > :is(text, a > text) {{ fill: {t['muted']} !important; }}
      .cluster > rect {{ rx: 3px; ry: 3px; stroke-width: 1px; }}
      .cluster-label .nodeLabel, .cluster-label .nodeLabel p, .cluster-label span {{
        font-size: 11px; font-weight: 500; letter-spacing: 0.09em; text-transform: uppercase; color: {t['muted']} !important; }}
      .edgeLabel, .edgeLabel p, .edgeLabel span {{ font-size: 12px; color: {t['muted']} !important; }}
      .edgeLabel rect, .labelBkg {{ fill: {t['paper']} !important; background: {t['paper']} !important; opacity: 1 !important; }}
      .flowchart-link, .transition {{ stroke-width: 1.25px; }}
      .marker, marker path {{ fill: {t['muted']} !important; stroke: {t['muted']} !important; }}
      .actor {{ stroke-width: 1px; }}
      .messageText, .loopText, .loopText > tspan, .labelText, .labelText > tspan, .noteText, .noteText > tspan {{ font-family: {FONT_SANS}; }}
      .messageText {{ fill: {t['ink']} !important; }}
      .labelText, .labelText > tspan {{ font-size: 11px; font-weight: 500; }}
      .loopLine {{ stroke-dasharray: 3 3; stroke: {t['rule-strong']} !important; }}
      .statediagram-state rect.basic, .statediagram-state rect.divider {{ rx: 3px; ry: 3px; }}
      .stateGroup rect, .statediagram-cluster rect.outer {{ rx: 3px; ry: 3px; }}
      .state-start, .state-end {{ fill: {t['ink']} !important; stroke: {t['ink']} !important; }}
      code, kbd, samp {{ font-family: {FONT_MONO}; font-size: inherit; background: none; color: inherit;
        padding: 0; margin: 0; border: 0; border-radius: 0; box-shadow: none; }}
      .flowchartTitleText, .titleText, .pieTitleText, .chart-title text, .chart-title, text.title, .journey-title,
      .c4-title, .packetTitle, .radarTitle, .treemapTitle, .quadrant-title, .timeline-title {{
        font-family: {FONT_SERIF} !important; font-weight: 600; fill: {t['ink']} !important; }}
    """


def theme_variables(t: Mapping[str, str], dark: bool) -> dict[str, Any]:
    cat = [t["accent"], t["info"], t["warning"], t["review"], t["danger"], t["success"], t["verify"], t["muted"]]
    cat_mid = [t[f"{n}-mid"] for n in ("accent", "info", "warning", "review", "danger", "success", "verify")]
    v: dict[str, Any] = {
        "darkMode": dark,
        "background": t["paper"],
        "fontFamily": FONT_SANS,
        "fontSize": f"{FONT_SIZE}px",
        "primaryColor": t["paper"],
        "primaryBorderColor": t["rule-strong"],
        "primaryTextColor": t["ink"],
        "secondaryColor": t["soft"],
        "secondaryBorderColor": t["rule-strong"],
        "secondaryTextColor": t["ink"],
        "tertiaryColor": t["soft"],
        "tertiaryBorderColor": t["rule"],
        "tertiaryTextColor": t["ink"],
        "lineColor": t["muted"],
        "textColor": t["ink"],
        "titleColor": t["ink"],
        "mainBkg": t["paper"],
        "nodeBorder": t["rule-strong"],
        "nodeTextColor": t["ink"],
        "clusterBkg": t["cluster-bg"],
        "clusterBorder": t["rule"],
        "edgeLabelBackground": t["paper"],
        "noteBkgColor": t["note-bg"],
        "noteBorderColor": t["note-border"],
        "noteTextColor": t["ink"],
        "actorBkg": t["paper"],
        "actorBorder": t["rule-strong"],
        "actorTextColor": t["ink"],
        "actorLineColor": t["rule-strong"],
        "signalColor": t["muted"],
        "signalTextColor": t["ink"],
        "labelBoxBkgColor": t["soft"],
        "labelBoxBorderColor": t["rule-strong"],
        "labelTextColor": t["ink"],
        "loopTextColor": t["muted"],
        "activationBkgColor": t["soft"],
        "activationBorderColor": t["rule-strong"],
        "sequenceNumberColor": t["paper"],
        "stateBkg": t["paper"],
        "stateBorder": t["rule-strong"],
        "stateLabelColor": t["ink"],
        "compositeBackground": t["cluster-bg"],
        "compositeTitleBackground": t["soft"],
        "altBackground": t["soft"],
        "transitionColor": t["muted"],
        "transitionLabelColor": t["muted"],
        "labelBackgroundColor": t["paper"],
        "specialStateColor": t["ink"],
        "innerEndBackground": t["ink"],
        "errorBkgColor": t["danger-bg"],
        "errorTextColor": t["danger"],
        # class / ER / requirement
        "classText": t["ink"],
        "attributeBackgroundColorOdd": t["paper"],
        "attributeBackgroundColorEven": t["soft"],
        "requirementBackground": t["paper"],
        "requirementBorderColor": t["rule-strong"],
        "requirementTextColor": t["ink"],
        "relationColor": t["muted"],
        "relationLabelBackground": t["paper"],
        "relationLabelColor": t["muted"],
        # gantt
        "sectionBkgColor": t["soft"],
        "altSectionBkgColor": t["paper"],
        "sectionBkgColor2": t["cluster-bg"],
        "taskBkgColor": t["accent-mid"],
        "taskBorderColor": t["accent"],
        "taskTextColor": t["ink"],
        "taskTextOutsideColor": t["ink"],
        "taskTextLightColor": t["ink"],
        "taskTextDarkColor": t["ink"],
        "activeTaskBkgColor": t["info-mid"],
        "activeTaskBorderColor": t["info"],
        "doneTaskBkgColor": t["soft"],
        "doneTaskBorderColor": t["rule-strong"],
        "critBkgColor": t["danger-mid"],
        "critBorderColor": t["danger"],
        "gridColor": t["rule"],
        "todayLineColor": t["danger"],
        "excludeBkgColor": t["soft"],
        # pie, quadrant, xychart and friends
        "pieTitleTextColor": t["ink"],
        "pieSectionTextColor": t["paper"],
        "pieLegendTextColor": t["ink"],
        "pieStrokeColor": t["paper"],
        "pieOuterStrokeColor": t["rule-strong"],
        "pieStrokeWidth": "1px",
        "pieOuterStrokeWidth": "1px",
        "pieOpacity": "1",
        "quadrant1Fill": t["accent-bg"],
        "quadrant2Fill": t["info-bg"],
        "quadrant3Fill": t["soft"],
        "quadrant4Fill": t["warning-bg"],
        "quadrant1TextFill": t["ink"],
        "quadrant2TextFill": t["ink"],
        "quadrant3TextFill": t["ink"],
        "quadrant4TextFill": t["ink"],
        "quadrantPointFill": t["accent"],
        "quadrantPointTextFill": t["ink"],
        "quadrantXAxisTextFill": t["muted"],
        "quadrantYAxisTextFill": t["muted"],
        "quadrantInternalBorderStrokeFill": t["rule-strong"],
        "quadrantExternalBorderStrokeFill": t["rule-strong"],
        "quadrantTitleFill": t["ink"],
        "xyChart": {
            "backgroundColor": t["paper"],
            "titleColor": t["ink"],
            "xAxisLabelColor": t["muted"],
            "xAxisTitleColor": t["ink"],
            "xAxisTickColor": t["rule-strong"],
            "xAxisLineColor": t["rule-strong"],
            "yAxisLabelColor": t["muted"],
            "yAxisTitleColor": t["ink"],
            "yAxisTickColor": t["rule-strong"],
            "yAxisLineColor": t["rule-strong"],
            "plotColorPalette": ", ".join(cat),
        },
        "fillType0": t["accent-bg"],
        "packet": {
            "startByteColor": t["muted"],
            "endByteColor": t["muted"],
            "labelColor": t["ink"],
            "titleColor": t["ink"],
            "blockStrokeColor": t["rule-strong"],
            "blockFillColor": t["soft"],
        },
    }
    for i, c in enumerate(cat_mid + cat_mid[:5]):
        v[f"pie{i + 1}"] = cat[i % len(cat)]
        v[f"cScale{i}"] = c
        v[f"cScaleLabel{i}"] = t["ink"]
        v[f"cScaleInv{i}"] = cat[i % len(cat)]
        v[f"cScalePeer{i}"] = cat[i % len(cat)]
    for i in range(8):
        v[f"git{i}"] = cat[i % len(cat)]
        v[f"gitInv{i}"] = t["paper"]
        v[f"gitBranchLabel{i}"] = t["paper"]
    v["commitLabelColor"] = t["ink"]
    v["commitLabelBackground"] = t["soft"]
    v["tagLabelColor"] = t["ink"]
    v["tagLabelBackground"] = t["soft"]
    v["tagLabelBorder"] = t["rule-strong"]
    return v


def mermaid_config(mode: str = "light", overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The config for mermaid.initialize() in the given palette ("light" or "dark"), with `overrides` merged in
    (nested dicts merge; anything else replaces)."""
    t = PALETTES[mode]
    config: dict[str, Any] = {
        "startOnLoad": False,
        "securityLevel": "strict",
        "theme": "base",
        "look": "classic",
        "layout": "elk",
        "htmlLabels": True,
        "maxEdges": 2000,
        "maxTextSize": 200_000,
        "fontFamily": FONT_SANS,
        "themeCSS": theme_css(t),
        "themeVariables": theme_variables(t, mode == "dark"),
        "flowchart": {"curve": "basis", "padding": 12, "wrappingWidth": 240, "minNodeWidth": 0, "nodeSpacing": 36,
                      "rankSpacing": 44, "diagramPadding": 8},
        "sequence": {"mirrorActors": False, "actorMargin": 56, "messageMargin": 30, "boxMargin": 8,
                     "noteMargin": 8, "width": 120, "height": 40, "actorFontSize": FONT_SIZE,
                     "messageFontSize": FONT_SIZE, "noteFontSize": FONT_SIZE - 1,
                     "actorFontFamily": FONT_SANS, "messageFontFamily": FONT_SANS, "noteFontFamily": FONT_SANS},
        # Mermaid 12 makes every flowchart and state label at least 120 px wide (minNodeWidth), which pads short
        # names out to wide boxes. Flowchart boxes have padding of their own; a state's is only 7 px, so 40 keeps
        # one-letter states from being slivers. States wrap like flowcharts.
        "state": {"padding": 10, "minNodeWidth": 40, "wrappingWidth": 240},
        # mermaid-diag's own layered-software diagram (js/layered_software.js).
        "layeredSoftware": {"titleFontFamily": FONT_SERIF},
        # and its state-machine diagram (js/state_machine.js).
        "stateMachine": {"codeFontFamily": FONT_MONO, "titleFontFamily": FONT_SERIF},
        "elk": {"mergeEdges": False, "nodePlacementStrategy": "BRANDES_KOEPF",
                "considerModelOrder": "NODES_AND_EDGES"},
    }
    config = merge(config, _FONT_SETTINGS)
    if overrides:
        config = merge(config, overrides)
    return config


# Diagram types with font settings of their own (Mermaid defaults most to "Open Sans", which a reader seldom has).
_C4_KINDS = ["person", "system", "system_db", "system_queue", "container", "container_db", "container_queue",
             "component", "component_db", "component_queue"]
_FONT_SETTINGS: dict[str, Any] = {
    "sequence": {},
    "journey": {"taskFontFamily": FONT_SANS, "titleFontFamily": FONT_SERIF},
    "timeline": {"taskFontFamily": FONT_SANS},
    "usecase": {"actorFontFamily": FONT_SANS, "usecaseFontFamily": FONT_SANS},
    "c4": {
        "boundaryFontFamily": FONT_SANS,
        "messageFontFamily": FONT_SANS,
        **{f"{kind}FontFamily": FONT_SANS for kind in _C4_KINDS},
        **{f"external_{kind}FontFamily": FONT_SANS for kind in _C4_KINDS},
    },
}


def merge(base: Mapping[str, Any], extra: Mapping[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(dict(base))
    for key, value in extra.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), Mapping):
            out[key] = merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out
