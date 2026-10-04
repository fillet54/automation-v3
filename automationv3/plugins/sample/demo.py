import hashlib
import json
import platform
import tempfile
from pathlib import Path

from automationv3.framework.uut import UUT, Environment, Version


class Sim(Environment):
    """A simulated environment rooted in a work directory"""

    name = "sim"

    def __init__(self, workdir=None, **params):
        super().__init__(workdir=workdir, **params)
        self.workdir = Path(workdir or Path(tempfile.gettempdir()) / "automationv3-sim")
        self.workdir.mkdir(parents=True, exist_ok=True)

    def fingerprint(self):
        return {
            "environment": self.name,
            "platform": platform.platform(),
            "python": platform.python_version(),
        }


class Demo(UUT):
    """A stub UUT with fixed versions"""

    name = "demo"
    VERSIONS = ["1.0.0", "1.1.0"]

    def list_versions(self):
        return [
            Version(id, hashlib.sha256(f"demo-{id}".encode()).hexdigest())
            for id in self.VERSIONS
        ]

    def _state(self, env):
        return env.workdir / "demo-installed.json"

    def installed_version(self, env):
        state = self._state(env)
        if not state.exists():
            return None
        return Version(**json.loads(state.read_text()))

    def install(self, version, env):
        if version not in self.list_versions():
            raise ValueError(f"demo has no version {version.id}")
        self._state(env).write_text(
            json.dumps({"id": version.id, "digest": version.digest})
        )

    def start(self, version, env):
        pass
