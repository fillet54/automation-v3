"""Renders in Node.js: one long-lived `node js/node_host.js` process, JSON lines over its stdin and stdout."""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import threading
from collections import deque
from functools import lru_cache
from typing import Any

from .base import FONTS_JSON, JS_DIR, Engine, EngineUnavailable, RenderError

MIN_NODE = (22, 12)  # what Mermaid 12 declares
DEFAULT_TIMEOUT = 600.0


def node_executable() -> str:
    exe = os.environ.get("MERMAID_DIAG_NODE") or shutil.which("node")
    if not exe:
        raise EngineUnavailable("node is not on PATH (set MERMAID_DIAG_NODE to its path)")
    return exe


@lru_cache(maxsize=None)
def _version_of(exe: str) -> str:
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30, check=True).stdout
    except (OSError, subprocess.SubprocessError) as e:
        raise EngineUnavailable(f"could not run {exe}: {e}") from None
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", out.strip())
    if not m:
        raise EngineUnavailable(f"unexpected `node --version` output: {out.strip()!r}")
    if (int(m[1]), int(m[2])) < MIN_NODE:
        raise EngineUnavailable(f"Node {m[0]} is too old: Mermaid 12 needs {MIN_NODE[0]}.{MIN_NODE[1]} or later")
    return f"{m[1]}.{m[2]}.{m[3]}"


def node_version() -> str:
    """The version of the Node that would be used, or EngineUnavailable."""
    return _version_of(node_executable())


class NodeEngine(Engine):
    name = "node"

    def __init__(self) -> None:
        self._exe = node_executable()
        self.version = _version_of(self._exe)
        self._proc: subprocess.Popen | None = None
        self._lines: queue.Queue = queue.Queue()
        self._stderr: deque[str] = deque(maxlen=40)
        self._lock = threading.Lock()
        self._next_id = 0

    def _start(self) -> None:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._proc = subprocess.Popen(
            [self._exe, str(JS_DIR / "node_host.js"), str(JS_DIR), str(FONTS_JSON)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", creationflags=flags,
        )
        self._lines = queue.Queue()
        proc, lines, stderr = self._proc, self._lines, self._stderr

        def read_stdout() -> None:
            for line in proc.stdout:
                lines.put(line)
            lines.put(None)

        def read_stderr() -> None:
            for line in proc.stderr:
                stderr.append(line.rstrip())

        threading.Thread(target=read_stdout, daemon=True, name="mermaid-diag-node-out").start()
        threading.Thread(target=read_stderr, daemon=True, name="mermaid-diag-node-err").start()
        ready = self._reply(60.0)
        if not ready.get("ready"):
            raise EngineUnavailable(f"node_host.js did not start: {ready}")

    def _reply(self, timeout: float) -> dict[str, Any]:
        try:
            line = self._lines.get(timeout=timeout)
        except queue.Empty:
            self._kill()
            raise RenderError(f"Node did not answer within {timeout:g}s (set MERMAID_DIAG_TIMEOUT to allow longer)") from None
        if line is None:
            tail = "\n".join(self._stderr)
            self._kill()
            raise RenderError("the Node process stopped" + (f":\n{tail}" if tail else ""))
        return json.loads(line)

    def _kill(self) -> None:
        if self._proc is not None:
            try:
                self._proc.kill()
                self._proc.wait(timeout=10)
            except (OSError, subprocess.SubprocessError):
                pass
            for stream in (self._proc.stdin, self._proc.stdout, self._proc.stderr):
                try:
                    stream.close()
                except (OSError, AttributeError):
                    pass
            self._proc = None

    def render(self, svg_id: str, source: str, config: dict[str, Any], timeout: float | None = None) -> str:
        timeout = timeout or float(os.environ.get("MERMAID_DIAG_TIMEOUT", DEFAULT_TIMEOUT))
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._start()
            self._next_id += 1
            req = {"id": self._next_id, "svgId": svg_id, "source": source, "config": config}
            try:
                self._proc.stdin.write(json.dumps(req) + "\n")
                self._proc.stdin.flush()
            except OSError as e:
                self._kill()
                raise RenderError(f"could not send the diagram to Node: {e}") from None
            reply = self._reply(timeout)
        if "error" in reply:
            raise RenderError(reply["error"])
        return reply["svg"]

    def close(self) -> None:
        with self._lock:
            if self._proc is not None:
                try:
                    self._proc.stdin.close()
                    self._proc.wait(timeout=5)
                except (OSError, subprocess.SubprocessError):
                    self._kill()
                for stream in (self._proc.stdout, self._proc.stderr) if self._proc else ():
                    try:
                        stream.close()
                    except OSError:
                        pass
                self._proc = None
