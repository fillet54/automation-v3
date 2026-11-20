"""Rendering a diagram: Mermaid source in, SVG (and PNG/PDF) out."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from . import __version__
from .engines import RenderError, get_engine
from .svgpost import Mismatch, merge_themes
from .theme import mermaid_config

MERMAID_VERSION = "12.2.0"
_VIEWBOX = re.compile(r'viewBox="\s*([-\d.e]+)[\s,]+([-\d.e]+)[\s,]+([-\d.e]+)[\s,]+([-\d.e]+)\s*"')


@dataclass(frozen=True)
class Diagram:
    """A rendered diagram.

    ``svg`` is what goes into a page: light and dark through CSS variables (or only light, when rendered with
    ``dark=False``). ``light`` is the light render with literal colours, the one for PNG and PDF.
    """

    svg: str
    light: str
    svg_id: str
    source: str = ""
    config: dict | None = None

    @property
    def size(self) -> tuple[float, float]:
        """Width and height in CSS pixels, from the viewBox."""
        m = _VIEWBOX.search(self.light)
        return (float(m[3]), float(m[4])) if m else (0.0, 0.0)

    def picture_svg(self, engine: str | None = None) -> str:
        """The light SVG to draw as a picture (see picture_svg())."""
        from . import cjk
        if self.source and cjk.needs_fallback(self.source):
            return picture_svg(self.source, "light", config=self.config, engine=engine, svg_id=self.svg_id)
        return self.light

    def png(self, scale: float = 2.0, background: str | None = None) -> bytes:
        from .raster import to_png
        return to_png(self.picture_svg(), scale, background)

    def pdf(self, scale: float = 3.0, background: str | None = None) -> bytes:
        from .raster import to_pdf
        return to_pdf(self.picture_svg(), scale, background)


def diagram_id(source: str, config: Mapping[str, Any] | None = None) -> str:
    """An id for the diagram's SVG made from its content: the same diagram keeps its id between builds."""
    digest = hashlib.sha1((source + json.dumps(config or {}, sort_keys=True)).encode()).hexdigest()
    return "md-" + digest[:10]


def _cache_key(*parts: Any) -> str:
    blob = json.dumps([__version__, MERMAID_VERSION, *parts], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def _cache_read(cache_dir: Path | None, key: str) -> dict | None:
    if cache_dir is None:
        return None
    path = Path(cache_dir) / key[:2] / f"{key}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _cache_write(cache_dir: Path | None, key: str, value: dict) -> None:
    if cache_dir is None:
        return
    folder = Path(cache_dir) / key[:2]
    folder.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(value, f)
    os.replace(tmp, folder / f"{key}.json")


def render(
    source: str,
    *,
    config: Mapping[str, Any] | None = None,
    dark: bool = True,
    theme_attribute: str = "data-theme",
    svg_id: str | None = None,
    engine: str | None = None,
    timeout: float | None = None,
    cache_dir: str | os.PathLike | None = None,
) -> Diagram:
    """Render Mermaid source.

    config: Mermaid config merged over mermaid-diag's own (see theme.mermaid_config). Applies to both palettes.
    dark: also render the dark palette, so the SVG follows dark mode. False gives a light-only SVG.
    theme_attribute: the root element attribute that forces a mode, ``<html data-theme="dark">``.
    svg_id: the SVG's id (default: made from the source, see diagram_id).
    engine: "auto" (default), "node" or "quickjs".
    cache_dir: keep renders here, keyed by everything that affects them.

    Raises RenderError with Mermaid's message when the diagram can't be rendered.
    """
    source = source.strip("\n")
    if not source.strip():
        raise RenderError("the diagram is empty")
    overrides = dict(config or {})
    svg_id = svg_id or diagram_id(source, overrides)
    if not re.fullmatch(r"[A-Za-z][\w-]*", svg_id):
        raise ValueError(f"not a usable SVG id: {svg_id!r}")
    # the full configs, not only the overrides: a change to the palette or fonts (theme.py) is a new render
    key = _cache_key(source, mermaid_config("light", overrides), mermaid_config("dark", overrides) if dark else None,
                     theme_attribute, svg_id)
    cached = _cache_read(Path(cache_dir) if cache_dir else None, key)
    if cached:
        return Diagram(svg=cached["svg"], light=cached["light"], svg_id=svg_id, source=source, config=overrides)

    js = get_engine(engine)
    light = js.render(svg_id, source, mermaid_config("light", overrides), timeout)
    svg = light
    if dark:
        dark_svg = js.render(svg_id, source, mermaid_config("dark", overrides), timeout)
        try:
            svg = merge_themes(light, dark_svg, svg_id, theme_attribute)
        except Mismatch:
            warnings.warn(f"{svg_id}: the dark render differs from the light one; the SVG is light only", stacklevel=2)
    _cache_write(Path(cache_dir) if cache_dir else None, key, {"svg": svg, "light": light})
    return Diagram(svg=svg, light=light, svg_id=svg_id, source=source, config=overrides)


def render_mode(source: str, mode: str, **kwargs: Any) -> str:
    """A single-palette SVG with literal colours: mode "light" or "dark"."""
    config = kwargs.pop("config", None)
    svg_id = kwargs.pop("svg_id", None) or diagram_id(source.strip("\n"), config)
    js = get_engine(kwargs.pop("engine", None))
    return js.render(svg_id, source.strip("\n"), mermaid_config(mode, config), kwargs.pop("timeout", None))


def picture_svg(source: str, mode: str = "light", **kwargs: Any) -> str:
    """A single-palette SVG for drawing as a PNG or PDF.

    Usually the same as render_mode(). When the diagram has characters the IBM Plex fonts lack (East Asian text,
    emoji), its labels are rendered as SVG text instead of HTML, and those characters are given fallback fonts
    (see mermaid_diag.cjk): novasvg can't switch fonts inside HTML labels."""
    from . import cjk
    from .theme import merge
    if not cjk.needs_fallback(source):
        return render_mode(source, mode, **kwargs)
    config = merge(kwargs.pop("config", None) or {}, {"htmlLabels": False, "flowchart": {"htmlLabels": False}})
    return cjk.wrap_runs(render_mode(source, mode, config=config, **kwargs))


__all__ = ["Diagram", "RenderError", "render", "render_mode", "picture_svg", "diagram_id", "MERMAID_VERSION"]
