"""Console lifecycle manager: borrows a worker and manages its Kernel."""

import shutil
import tempfile
import threading
import time
from pathlib import Path

from ...framework import closure as closures
from .kernel import Kernel, KernelError, newest

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
