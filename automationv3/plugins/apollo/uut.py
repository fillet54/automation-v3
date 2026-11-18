"""The lunar module as a unit under test: its versions (Luminary ropes),
installing one, and booting it

Versions are ropes (see model/rope.py): the three released Luminary
revisions, and any local builds uploaded to the build repository, the
folder named by AUTOMATION_LM_BUILDS (one subfolder per build, holding
its luminary.json). Uploaded builds are for scratch runs only.

What is installed, and the flight, live in the environment's work
directory, so every run on that environment sees the same LM. Booting
to a start point after PDI flies there with the nominal crew; the result
is cached in the work directory, keyed by everything that shapes the
flight, so the next boot to the same point is a file read.
"""

import hashlib
import json
import os
import shutil
from pathlib import Path

from automationv3.framework.uut import UUT, LocalBuild, Version

from .model import missions as M
from .model import rope as R
from .model import sim


class LunarModule(UUT):
    """The Apollo lunar module and its guidance computer. Its handle is `lm`."""

    name = "lm"
    BUILD = "luminary.json"

    # Versions and builds

    def list_versions(self):
        """The released ropes, then any uploaded builds, oldest first"""
        released = [Version(id, R.digest(rope)) for id, rope in R.RELEASES.items()]
        return released + [Version(id, R.digest(rope)) for id, rope in self.uploaded()]

    def report_versions(self):
        return [v for v in self.list_versions() if v.id in R.RELEASES]

    @staticmethod
    def build_repo():
        path = os.environ.get("AUTOMATION_LM_BUILDS")
        return Path(path) if path else None

    def uploaded(self):
        """(id, rope) for every build in the build repository, oldest first"""
        repo = self.build_repo()
        if repo is None or not repo.is_dir():
            return []
        builds = sorted((p for p in repo.iterdir() if (p / self.BUILD).is_file()),
                        key=lambda p: ((p / self.BUILD).stat().st_mtime, p.name))
        found = []
        for folder in builds:
            try:
                found.append((folder.name, R.parse((folder / self.BUILD).read_text())))
            except ValueError:
                continue
        return found

    def rope(self, version):
        if version.id in R.RELEASES:
            return R.RELEASES[version.id]
        rope = dict(self.uploaded()).get(version.id)
        if rope is None:
            raise ValueError(f"lm has no version {version.id}")
        return rope

    def find_local_build(self, path):
        build = Path(path) / self.BUILD
        if not build.is_file():
            return None
        found = R.digest(R.parse(build.read_text()))
        return LocalBuild(self.name, build, f"local-{found[:12]}", found, build.stat().st_mtime)

    def upload_build(self, build):
        repo = self.build_repo()
        if repo is None:
            raise RuntimeError("Set AUTOMATION_LM_BUILDS to the lunar module's build repository")
        (repo / build.id).mkdir(parents=True, exist_ok=True)
        shutil.copy2(build.path, repo / build.id / self.BUILD)
        return Version(build.id, build.digest)

    # The state on an environment

    def path(self, env):
        return Path(env.workdir) / "lm-state.json"

    def load(self, env):
        path = self.path(env)
        if path.exists():
            return json.loads(path.read_text())
        return {"installed": None, "rope": None, "flight": None, "wall": None}

    def save(self, env, state):
        path = self.path(env)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, separators=(",", ":")))
        tmp.replace(path)

    def installed_version(self, env):
        installed = self.load(env)["installed"]
        return Version(**installed) if installed else None

    def install(self, version, env):
        if version not in self.list_versions():
            raise ValueError(f"lm has no version {version.id}")
        self.save(env, {"installed": {"id": version.id, "digest": version.digest},
                        "rope": self.rope(version), "flight": None, "wall": None})

    def start(self, version, env):
        """Boot fresh: a standard mission at PDI, with the nominal crew"""
        state = self.load(env)
        state["flight"] = self.boot(state["rope"], {}, env)
        state["wall"] = None
        self.save(env, state)

    def boot(self, rope, config, env):
        """A flight booted for `config`; raises sim.BootRejected if the
        rope won't take the load"""
        if rope is None:
            raise RuntimeError("lm isn't installed in this environment")
        c = sim.configuration(config)
        settings = environment_settings(env)
        key = hashlib.sha256(json.dumps(
            [M.MODEL_VERSION, R.digest(rope), {**c, "crew": None}, settings],
            sort_keys=True).encode()).hexdigest()[:24]
        cache = Path(env.workdir) / "lm-starts" / f"{key}.json"
        if c["start"] != "pdi" and cache.exists():
            flight = json.loads(cache.read_text())
        else:
            flight = sim.boot(rope, {**c, "crew": "nominal"}, settings)
            if c["start"] != "pdi":
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(flight, separators=(",", ":")))
        flight["config"]["crew"] = c["crew"]
        flight["crew"] = sim.C.fresh(c["crew"])
        return flight

    def handle(self, version, env):
        from .handle import LunarModuleHandle
        return LunarModuleHandle(self, env)


def environment_settings(env):
    """What the environment changes in a flight (see environments.py)"""
    settings = getattr(env, "settings", None)
    return settings() if callable(settings) else {}
