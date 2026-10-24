import hashlib
import json
import os
import platform
import shutil
import tempfile
from pathlib import Path

from automationv3.framework import edn
from automationv3.framework.uut import UUT, Environment, LocalBuild, Version


class Sim(Environment):
    """A simulated environment rooted in a work directory"""

    name = "sim"

    def __init__(self, workdir=None, **params):
        super().__init__(workdir=workdir, **params)
        default = Path(tempfile.gettempdir()) / f"automationv3-{self.name}"
        self.workdir = Path(workdir or default)
        self.workdir.mkdir(parents=True, exist_ok=True)

    def fingerprint(self):
        return {
            "environment": self.name,
            "platform": platform.platform(),
            "python": platform.python_version(),
        }

    def clock(self, handles):
        """The simulated Vehicle Manager's time, when it is under test"""
        vm = handles.get("vm")
        return vm.clock() if vm is not None else None


class Bench(Sim):
    """A stand-in for a hardware bench; behaves like the simulator"""

    name = "bench"


class Demo(UUT):
    """A stub UUT: a tiny simulated vehicle with fixed versions.

    Its state lives in the environment's work directory: the installed
    version, whether it is running and in which mode, named readings
    (e.g. brake pressure) and active faults. Installing a version stops
    it; starting it fresh clears mode, readings and faults.
    """

    name = "demo"
    VERSIONS = ["1.0.0", "1.1.0"]
    BUILD = "demo.bin"  # what a demo build is: one file

    def list_versions(self):
        """The released versions, then any uploaded builds, oldest first"""
        released = [
            Version(id, hashlib.sha256(f"demo-{id}".encode()).hexdigest())
            for id in self.VERSIONS
        ]
        return released + self.uploaded()

    # Builds. The demo's build repository is a folder (in real life, a git
    # repository with its own clean-up): AUTOMATION_DEMO_BUILDS, one
    # subfolder per uploaded build holding its demo.bin.

    @staticmethod
    def build_repo():
        path = os.environ.get("AUTOMATION_DEMO_BUILDS")
        return Path(path) if path else None

    def report_versions(self):
        """Only the released versions: uploaded builds are for scratch"""
        return [v for v in self.list_versions() if v.id in self.VERSIONS]

    def uploaded(self):
        repo = self.build_repo()
        if repo is None or not repo.is_dir():
            return []
        builds = sorted((p for p in repo.iterdir() if (p / self.BUILD).is_file()),
                        key=lambda p: (p / self.BUILD).stat().st_mtime)
        return [Version(p.name, digest(p / self.BUILD)) for p in builds]

    def find_local_build(self, path):
        build = Path(path) / self.BUILD
        if not build.is_file():
            return None
        found = digest(build)
        return LocalBuild(self.name, build, f"local-{found[:12]}", found,
                          build.stat().st_mtime)

    def upload_build(self, build):
        repo = self.build_repo()
        if repo is None:
            raise RuntimeError("Set AUTOMATION_DEMO_BUILDS to the demo's build repository")
        (repo / build.id).mkdir(parents=True, exist_ok=True)
        shutil.copy2(build.path, repo / build.id / self.BUILD)
        return Version(build.id, build.digest)

    def state(self, env):
        path = env.workdir / "demo-state.json"
        if path.exists():
            return json.loads(path.read_text())
        return {"installed": None, "running": False, "mode": None,
                "readings": {}, "faults": []}

    def save(self, env, state):
        (env.workdir / "demo-state.json").write_text(json.dumps(state))

    def installed_version(self, env):
        installed = self.state(env)["installed"]
        return Version(**installed) if installed else None

    def install(self, version, env):
        if version not in self.list_versions():
            raise ValueError(f"demo has no version {version.id}")
        installed = {"id": version.id, "digest": version.digest}
        self.save(env, {**self.state(env), "installed": installed,
                        "running": False, "mode": None})

    def start(self, version, env):
        self.save(env, {**self.state(env), "running": True, "mode": None,
                        "readings": {}, "faults": []})

    def handle(self, version, env):
        return DemoHandle(self, env)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def key(name):
    return edn.writes(name)


class DemoHandle:
    """What scripts see as `demo`. Actions return true so they can be steps."""

    def __init__(self, uut, env):
        self.uut, self.env = uut, env

    def _update(self, **changes):
        self.uut.save(self.env, {**self.uut.state(self.env), **changes})
        return True

    def running(self):
        return self.uut.state(self.env)["running"]

    def mode(self):
        mode = self.uut.state(self.env)["mode"]
        return edn.read(mode) if mode else None

    def version(self):
        installed = self.uut.state(self.env)["installed"]
        return installed["id"] if installed else None

    def start(self, mode):
        """Restart in `mode`: readings and faults are cleared"""
        return self._update(running=True, mode=key(mode), readings={}, faults=[])

    def stop(self):
        return self._update(running=False, mode=None)

    def get(self, name):
        return self.uut.state(self.env)["readings"].get(key(name))

    def set(self, name, value):
        readings = self.uut.state(self.env)["readings"]
        return self._update(readings={**readings, key(name): value})

    def fault(self, name):
        faults = self.uut.state(self.env)["faults"]
        return self._update(faults=sorted(set(faults) | {key(name)}))

    def faults(self):
        return [edn.read(f) for f in self.uut.state(self.env)["faults"]]

    def has_fault(self, name):
        return key(name) in self.uut.state(self.env)["faults"]

    def clear_faults(self):
        return self._update(faults=[])
