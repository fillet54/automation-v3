"""What a worker can run: hosted environments and installable UUTs

A worker's config names the environments it hosts and their params::

    {"environments": {"sim": {"workdir": "/tmp/sim"}, "bench": {}}}

Every UUT whose plugin is loaded can be installed.

An environment's fingerprint is what its plugin reports, plus the
framework running it (version, git hash, and whether it is a source
checkout with uncommitted changes): runs are only identical when all of
it matches.
"""

import json
from pathlib import Path

from ...framework.uut import environment_types, uut_types
from ..util import framework_fingerprint  # noqa: F401


def read_config(path):
    """Parse a worker's JSON config file, or {} when no path is given"""
    return json.loads(Path(path).read_text()) if path else {}


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
        return cls.from_config(read_config(path))

    def fingerprint(self, name):
        """Environment `name`'s fingerprint, with the framework's"""
        return {**self.environments[name].fingerprint(),
                "framework": framework_fingerprint()}

    def capabilities(self):
        return {
            "uut_types": sorted(self.uuts),
            "environments": {
                name: self.fingerprint(name) for name in self.environments
            },
        }
