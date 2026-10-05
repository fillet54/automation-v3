"""What a worker can run: hosted environments and installable UUTs

A worker's config names the environments it hosts and their params::

    {"environments": {"sim": {"workdir": "/tmp/sim"}, "bench": {}}}

Every UUT whose plugin is loaded can be installed.
"""

import json

from ...framework.uut import environment_types, uut_types


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

    def capabilities(self):
        return {
            "uut_types": sorted(self.uuts),
            "environments": {
                name: env.fingerprint() for name, env in self.environments.items()
            },
        }
