"""What a worker can run: hosted environments and installable UUTs

A worker's config names the environments it hosts and their params::

    {"environments": {"sim": {"workdir": "/tmp/sim"}, "bench": {}}}

Every UUT whose plugin is loaded can be installed.

An environment's fingerprint is what its plugin reports, plus the
framework running it (version, git hash, and whether it is a source
checkout with uncommitted changes): runs are only identical when all of
it matches.
"""

import functools
import json
import subprocess
from pathlib import Path

from ... import __version__
from ...framework.uut import environment_types, uut_types

PACKAGE = Path(__file__).resolve().parents[2]


@functools.lru_cache(maxsize=1)
def framework_fingerprint():
    """The framework's version; for a git checkout, its commit and
    whether it has uncommitted changes (a dev install)"""
    def git(*args):
        return subprocess.run(["git", *args], cwd=PACKAGE, capture_output=True,
                              text=True, timeout=10)
    try:
        head = git("rev-parse", "HEAD")
    except (OSError, subprocess.SubprocessError):
        head = None
    if head is None or head.returncode != 0:
        return {"version": __version__, "git": None, "dev": False}
    dirty = git("status", "--porcelain", "--untracked-files=no").stdout.strip()
    return {"version": __version__, "git": head.stdout.strip(), "dev": bool(dirty)}


class Host:
    def __init__(self, environments=None):
        self.environments = environments or {}
        self.uuts = {name: cls() for name, cls in uut_types().items()}

    @classmethod
    def from_config(cls, config):
        types = environment_types()
        environments = {}
        for name, params in config.get("environments", {}).items():
            if name not in types:
                raise ValueError(f"No environment plugin named {name}")
            environments[name] = types[name](**(params or {}))
        return cls(environments)

    @classmethod
    def from_file(cls, path):
        return cls.from_config(json.loads(open(path).read()) if path else {})

    def fingerprint(self, name):
        """Environment `name`'s fingerprint, with the framework's"""
        return {**self.environments[name].fingerprint(),
                "framework": framework_fingerprint()}

    def capabilities(self):
        return {
            "uut_types": sorted(self.uuts),
            "environments": {name: self.fingerprint(name) for name in self.environments},
        }
