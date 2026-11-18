"""The editor's console: a kernel (services/worker/kernel.py) on this
machine, run from the workspace page

There is one console per app, and only where the app has a worker in
its own process (CONSOLE_WORKER: client --config, server --local-worker,
demo). Opening it borrows that worker, so the worker takes no jobs until
the console is closed, or has been idle for CONSOLE_IDLE seconds.

The console is bound to one script of one workspace (its core.rst
chain, its UUTs, its variations). The page sends it cards and forms to
run, and asks for the transcript lines after the last it has.

Routes, on the workspace blueprint (`/workspace/<id>/console...`):

    GET  console?path=P         whether a console is possible, its state,
                                and the choices for script P
    GET  console/lines?since=N  transcript lines after N, and the state
    POST console/open           {path, environment, versions, variation}
    POST console/run            {kind: "card", code, title, definitions,
                                 table, variations}
                                {kind: "form", code, line, character}: the
                                 form at the cursor in a card's code
                                {kind: "forms", text, line, character}
    POST console/<control>      stop, reset, restart, release, clear, close
    GET  console/files/<name>   a file a block attached
"""

import shutil
import tempfile
import threading
import time
from pathlib import Path

from flask import abort, current_app, jsonify, request, send_from_directory

from ..framework import closure as closures
from ..services.worker.kernel import Kernel, KernelError, find_form, newest

IDLE = 30 * 60  # seconds an idle console is kept open
BORROW_WAIT = 30  # seconds to wait for the worker's running job


class Console:
    """The app's one console: the worker it borrows, and the kernel"""

    def __init__(self, worker, idle=IDLE):
        self.worker, self.idle = worker, idle
        self.kernel = None
        self.workspace = None
        self.files = None
        self.lock = threading.RLock()
        self.watching = False

    def state(self):
        if self.kernel is None:
            return None
        return {**self.kernel.state(), "workspace": self.workspace}

    def open(self, workspace, root, script, **choices):
        """Open a kernel on `script`, closing the one open first. Raises
        KernelError if it can't."""
        with self.lock:
            self.close()
            if not self.worker.borrow(timeout=BORROW_WAIT):
                raise KernelError("The local worker is still running a job; "
                                  "try again when it is done")
            files = Path(tempfile.mkdtemp(prefix="automation-console-"))
            try:
                kernel = Kernel(self.worker.host, root, script, files_dir=files, **choices)
            except Exception:
                shutil.rmtree(files, ignore_errors=True)
                self.worker.give_back()
                raise
            self.kernel, self.workspace, self.files = kernel, workspace, files
            kernel.open()
            self._watch()
            return kernel

    def close(self):
        with self.lock:
            if self.kernel is None:
                return
            kernel, files = self.kernel, self.files
            self.kernel = self.workspace = self.files = None
            kernel.close()
            kernel.wait_idle(10)
            shutil.rmtree(files, ignore_errors=True)
            self.worker.give_back()

    def close_if_idle(self):
        with self.lock:
            kernel = self.kernel
            if kernel is not None and not kernel.busy() \
                    and time.monotonic() - kernel.used > self.idle:
                self.close()

    def _watch(self):
        """Close the console once it has been idle long enough, even if no
        page asks"""
        if self.watching:
            return
        self.watching = True

        def watch():
            while True:
                time.sleep(min(60, max(1, self.idle / 4)))
                self.close_if_idle()

        threading.Thread(target=watch, name="console-idle", daemon=True).start()


def console():
    """The app's Console, or None where the app has no worker in process"""
    config = current_app.config
    worker = config.get("CONSOLE_WORKER")
    if worker is None:
        return None
    found = config.get("_CONSOLE")
    if found is None:
        found = config["_CONSOLE"] = Console(worker, config.get("CONSOLE_IDLE", IDLE))
    found.close_if_idle()
    return found


def choices(host, root, script):
    """What a console on `script` can be opened with, and the defaults"""
    try:
        found = closures.resolve(root, script)
    except (OSError, ValueError) as e:
        return {"error": f"Can't read {script}: {e}"}
    environments = [e for e in (found.environments or host.environments)
                    if e in host.environments]
    versions, defaults = {}, {}
    for name in found.uuts:
        uut = host.uuts.get(name)
        if uut is None:
            return {"error": f"No UUT plugin for {name}"}
        versions[name] = [v.id for v in uut.list_versions()]
        default = newest(uut)
        if default is not None:
            defaults[name] = default.id
    if not environments:
        return {"error": f"This machine hosts none of {script}'s environments "
                         f"({', '.join(found.environments) or 'none declared'})"}
    return {
        "script": script,
        "environments": environments,
        "versions": versions,
        "variations": [v.name for v in found.variations],
        "defaults": {"environment": environments[0], "versions": defaults,
                     "variation": found.variations[0].name if found.variations else None},
    }


def register(bp, workspace_or_404, node_or_404, editable):
    def available(id):
        """(workspace, the app's console), or 404 where there is none"""
        if not editable():
            abort(403)
        ws = workspace_or_404(id)
        found = console()
        if found is None:
            abort(404)
        return ws, found

    def body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            abort(400)
        return data

    def refuse(message, status=409):
        response = jsonify(error=message)
        response.status_code = status
        abort(response)

    def kernel_of(ws, found):
        """The open kernel, if it is this workspace's"""
        kernel = found.kernel
        if kernel is None:
            refuse("The console isn't open")
        if found.workspace != ws.id:
            refuse(f"The console is open on {found.workspace}; close it there first")
        return kernel

    def script_path(ws, path):
        node = node_or_404(ws, path or "")
        if not node.is_file():
            refuse("Save the script first: the console loads it from disk", 400)
        return str(node.relative_path)

    @bp.route("/<path:id>/console", methods=["GET"])
    def console_state(id):
        ws, found = available(id)
        answer = {"state": found.state()}
        path = request.args.get("path")
        if path:
            node = node_or_404(ws, path)
            answer["choices"] = (choices(found.worker.host, ws.root, str(node.relative_path))
                                 if node.is_file() else {"error": "Save the script first"})
        return jsonify(answer)

    @bp.route("/<path:id>/console/lines", methods=["GET"])
    def console_lines(id):
        ws, found = available(id)
        try:
            since = int(request.args.get("since", 0))
        except ValueError:
            abort(400)
        kernel = found.kernel
        if kernel is None or found.workspace != ws.id:
            return jsonify(lines=[], state=found.state())
        return jsonify(lines=kernel.lines_since(since), state=found.state())

    @bp.route("/<path:id>/console/open", methods=["POST"])
    def console_open(id):
        ws, found = available(id)
        data = body()
        script = script_path(ws, data.get("path"))
        versions = data.get("versions") or {}
        if not isinstance(versions, dict):
            abort(400)
        try:
            found.open(ws.id, ws.root, script,
                       environment=data.get("environment") or None,
                       versions={str(k): str(v) for k, v in versions.items() if v},
                       variation=data.get("variation") or None)
        except KernelError as e:
            refuse(str(e))
        return jsonify(state=found.state())

    @bp.route("/<path:id>/console/run", methods=["POST"])
    def console_run(id):
        ws, found = available(id)
        kernel = kernel_of(ws, found)
        data = body()
        kind = data.get("kind")
        variations = data.get("variations") or []
        if not isinstance(variations, list):
            abort(400)
        try:
            if kind == "card":
                command = kernel.run_card(
                    str(data.get("code") or ""), title=data.get("title") or None,
                    definitions=bool(data.get("definitions")), table=bool(data.get("table")),
                    variations=variations)
            elif kind == "form":
                line, character = data.get("line"), data.get("character")
                if not isinstance(line, int) or not isinstance(character, int):
                    abort(400)
                at = find_form(str(data.get("code") or ""), line, character)
                if at is None:
                    refuse("There is no form at the cursor", 400)
                text, line, character = at
                command = kernel.run_forms(text, line=line, character=character,
                                           variations=variations)
            elif kind == "forms":
                text = str(data.get("text") or "")
                if not text.strip():
                    refuse("Nothing to run", 400)
                line, character = data.get("line") or 0, data.get("character") or 0
                if not isinstance(line, int) or not isinstance(character, int):
                    abort(400)
                command = kernel.run_forms(text, line=line, character=character,
                                           variations=variations)
            else:
                abort(400)
        except KernelError as e:
            refuse(str(e))
        return jsonify(command=command.id, state=found.state())

    @bp.route("/<path:id>/console/<any(stop, reset, restart, release, clear, close):control>",
              methods=["POST"])
    def console_control(id, control):
        ws, found = available(id)
        if control == "close":
            if found.kernel is not None and found.workspace == ws.id:
                found.close()
            return jsonify(state=found.state())
        kernel = kernel_of(ws, found)
        try:
            if control == "stop":
                kernel.stop()
            elif control == "reset":
                kernel.reset()
            elif control == "restart":
                kernel.restart(abandon=True)
            elif control == "release":
                kernel.release()
            elif control == "clear":
                kernel.clear()
        except KernelError as e:
            refuse(str(e))
        return jsonify(state=found.state())

    @bp.route("/<path:id>/console/files/<name>", methods=["GET"])
    def console_file(id, name):
        ws, found = available(id)
        if found.files is None or found.workspace != ws.id:
            abort(404)
        return send_from_directory(found.files, name)
