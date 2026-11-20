"""Renders in QuickJS-ng (the quickjs-ng wheel): no Node needed.

A fresh context per diagram (Mermaid keeps counters between renders, a browser page starts from zero), all on one
worker thread with a large stack: QuickJS contexts aren't thread-safe, and deep layouts recurse far.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any

from .base import Engine, EngineUnavailable, RenderError, page_scripts

try:
    import quickjs
except ImportError:  # pragma: no cover
    quickjs = None

_THREAD_STACK = 64 * 1024 * 1024
_JS_STACK = 48 * 1024 * 1024
_MEMORY = 2 * 1024 * 1024 * 1024
_MAX_STEPS = 2_000_000

# QuickJS keeps long concatenations as ropes, which the binding can't hand to Python; slice(0) flattens one.
_FLAT = "globalThis.__flat = (v) => (typeof v === 'string' ? v.slice(0) : v);"


class QuickJSEngine(Engine):
    name = "quickjs"

    def __init__(self) -> None:
        if quickjs is None:
            raise EngineUnavailable("quickjs-ng is not installed (pip install quickjs-ng)")
        self._executor: ThreadPoolExecutor | None = None
        self._ctx = None
        self._lock = threading.Lock()

    def _ensure_started(self) -> None:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mermaid-diag-quickjs")
            previous = threading.stack_size(_THREAD_STACK)
            try:
                self._executor.submit(self._prepare).result()
            finally:
                threading.stack_size(previous)

    def _new_context(self):
        ctx = quickjs.Context()
        ctx.set_memory_limit(_MEMORY)
        ctx.set_max_stack_size(_JS_STACK)
        if os.environ.get("MERMAID_DIAG_DEBUG"):
            ctx.add_callable("__log_raw", lambda s: print(f"[mermaid-diag] {s}", file=sys.stderr))
        else:
            ctx.add_callable("__log_raw", lambda s: None)
        ctx.eval(_FLAT + "globalThis.__log = (s) => __log_raw(__flat(String(s)));")
        for _name, source in page_scripts():
            ctx.eval(source)
        return ctx

    def _prepare(self) -> None:
        if self._ctx is None:
            self._ctx = self._new_context()

    def _render_sync(self, svg_id: str, source: str, config: dict[str, Any]) -> str:
        self._prepare()
        ctx, self._ctx = self._ctx, None
        ctx.eval(f"__mdRender({json.dumps(svg_id)}, {json.dumps(source)}, {json.dumps(config)});")
        for _ in range(_MAX_STEPS):
            if ctx.eval("__mdDone()"):
                break
            try:
                if ctx.execute_pending_job():
                    continue
            except StopIteration:
                pass
            if not ctx.eval("__runNextTimer()"):
                break
        if not ctx.eval("__mdDone()"):
            raise RenderError("the render stopped before it finished")
        error = ctx.eval("__flat(globalThis.__mdError)")
        if error is not None:
            raise RenderError(str(error))
        return str(ctx.eval("__flat(globalThis.__mdResult)"))

    def render(self, svg_id: str, source: str, config: dict[str, Any], timeout: float | None = None) -> str:
        with self._lock:
            self._ensure_started()
            future = self._executor.submit(self._render_sync, svg_id, source, config)
            try:
                result = future.result(timeout=timeout)
            except FutureTimeout:
                raise RenderError(f"QuickJS did not finish within {timeout:g}s") from None
            except RenderError:
                self._executor.submit(self._prepare)
                raise
            except Exception as e:  # a JavaScript exception from the binding
                self._executor.submit(self._prepare)
                raise RenderError(str(e)) from None
            self._executor.submit(self._prepare)  # the next page, while the caller is busy
            return result

    def close(self) -> None:
        with self._lock:
            if self._executor is not None:
                self._executor.shutdown(wait=True)
                self._executor = None
                self._ctx = None
