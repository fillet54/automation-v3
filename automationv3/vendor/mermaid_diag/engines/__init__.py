"""The JavaScript engines a diagram can be rendered in.

Both run the same page (js/: fonts.json, metrics.js, path_bbox.js, dom_shim.js, mermaid.min.js with its ELK exposed
(base.expose_elk), layered_software.js, state_machine.js, driver.js), so they give the same SVG:

- ``node``: Node.js 22.12 or later, found on PATH (or MERMAID_DIAG_NODE). Fast (V8), one process for many renders.
- ``quickjs``: QuickJS-ng from the quickjs-ng wheel. Always available, slower on large diagrams.

``auto`` (the default) uses Node when it is there and QuickJS otherwise. MERMAID_DIAG_ENGINE overrides it.
"""

from __future__ import annotations

import os
import threading

from .base import Engine, EngineUnavailable, RenderError

__all__ = ["Engine", "EngineUnavailable", "RenderError", "get_engine", "available_engines", "close_engines"]

_engines: dict[str, Engine] = {}
_lock = threading.Lock()
_pid = os.getpid()


def _make(name: str) -> Engine:
    if name == "node":
        from .node import NodeEngine
        return NodeEngine()
    if name == "quickjs":
        from .quickjs import QuickJSEngine
        return QuickJSEngine()
    raise ValueError(f"unknown engine {name!r}: use auto, node or quickjs")


def available_engines() -> dict[str, str]:
    """{name: version or why it is unavailable} for each engine."""
    from .node import node_version
    out = {}
    try:
        out["node"] = "Node " + node_version()
    except EngineUnavailable as e:
        out["node"] = f"unavailable: {e}"
    try:
        import quickjs  # noqa: F401
        out["quickjs"] = "QuickJS-ng"
    except ImportError as e:
        out["quickjs"] = f"unavailable: {e}"
    return out


def get_engine(name: str | None = None) -> Engine:
    """The shared engine of that name ("auto", "node" or "quickjs"), started on first use."""
    global _pid
    name = (name or os.environ.get("MERMAID_DIAG_ENGINE") or "auto").lower()
    with _lock:
        if _pid != os.getpid():
            # A forked process (Sphinx's parallel builds) must not share its parent's Node pipes or QuickJS thread.
            _engines.clear()
            _pid = os.getpid()
        if name == "auto":
            if "auto" not in _engines:
                try:
                    from .node import node_version
                    node_version()
                    _engines["auto"] = _engines.get("node") or _make("node")
                except EngineUnavailable:
                    _engines["auto"] = _engines.get("quickjs") or _make("quickjs")
            return _engines["auto"]
        if name not in _engines:
            _engines[name] = _make(name)
        return _engines[name]


def close_engines() -> None:
    with _lock:
        for engine in set(_engines.values()):
            engine.close()
        _engines.clear()
