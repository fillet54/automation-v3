from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

PACKAGE = Path(__file__).resolve().parent.parent
JS_DIR = PACKAGE / "js"
FONTS_JSON = PACKAGE / "fonts" / "fonts.json"

# The page's scripts, in the order they are run in every fresh page.
PAGE_SCRIPTS = ("prelude.js", "metrics.js", "path_bbox.js", "dom_shim.js", "mermaid.min.js", "layered_software.js", "state_machine.js",
                "driver.js")


class RenderError(RuntimeError):
    """Mermaid could not render the diagram (a syntax error, usually); the message is Mermaid's."""


class EngineUnavailable(RuntimeError):
    """The engine can't run here (Node missing or too old, quickjs-ng not installed)."""


def expose_elk(bundle: str) -> str:
    """mermaid.min.js with its copy of elkjs's ELK class reachable as ``globalThis.__mdELK()``.

    Mermaid bundles elkjs for its ELK layout but keeps the class to itself; state-machine (js/state_machine.js)
    lays out with it directly, with options of its own. The minified names change between Mermaid builds, so
    they are found from the one place Mermaid creates an ELK (``new X.default; ....log.info("Drawing flowchart
    using v4 renderer"``) and the module that holds it (``X=interop(require(),1)``). node_host.js does the same.
    """
    m = re.search(r'new (\w+)\.default;\w+\.log\.info\("Drawing flowchart using v4 renderer"', bundle)
    if not m:
        raise RuntimeError("mermaid.min.js: can't find where Mermaid creates its ELK (see expose_elk)")
    name = re.escape(m[1])
    load = re.search(rf"[,;{{]{name}=(\w+)\((\w+)\(\),1\)", bundle)
    decl = list(re.finditer(rf"(?<![\w$])var {name},", bundle))
    if not load or len(decl) != 1:
        raise RuntimeError("mermaid.min.js: can't find Mermaid's ELK module (see expose_elk)")
    hook = f"globalThis.__mdELK=()=>{load[1]}({load[2]}(),1).default;"
    at = decl[0].start()
    return bundle[:at] + hook + bundle[at:]


def _script(name: str) -> str:
    text = (JS_DIR / name).read_text(encoding="utf-8")
    return expose_elk(text) if name == "mermaid.min.js" else text


@lru_cache(maxsize=1)
def page_scripts() -> tuple[tuple[str, str], ...]:
    """(name, source) of each script a page runs, fonts first."""
    fonts = "globalThis.__MD_FONTS = " + FONTS_JSON.read_text(encoding="utf-8") + ";"
    return (("fonts.json", fonts),) + tuple((name, _script(name)) for name in PAGE_SCRIPTS)


class Engine:
    """Renders Mermaid source to SVG text. Safe to share between threads (renders take turns)."""

    name = "engine"

    def render(self, svg_id: str, source: str, config: dict[str, Any], timeout: float | None = None) -> str:
        raise NotImplementedError

    def close(self) -> None:
        pass


def request(svg_id: str, source: str, config: dict[str, Any]) -> str:
    return json.dumps({"svgId": svg_id, "source": source, "config": config})
