"""Units under test and the environments they run in

Both are extension points. Plugins in `automationv3.plugins` subclass
`UUT` or `Environment` and set `name`; tests declare which they need
with `(uut :name)` and `(environments :name ...)`.

The server calls `UUT.list_versions` to offer versions when queuing.
Workers host Environment instances (configured per worker) and call
`installed_version` / `install` before running a job.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Version:
    """A UUT version. The digest identifies the exact bits."""

    id: str
    digest: str


class Environment:
    """A runtime target hosted by a worker, e.g. a simulator or a bench"""

    name = None

    def __init__(self, **params):
        self.params = params

    def fingerprint(self):
        """Facts about this environment that can affect results"""
        return {}


class UUT:
    """A unit under test that can be installed into an environment"""

    name = None

    def list_versions(self):
        """Every installable Version, oldest first"""
        return []

    def find_version(self, id):
        return next((v for v in self.list_versions() if v.id == id), None)

    def installed_version(self, env):
        """The Version currently installed in `env`, or None"""
        return None

    def install(self, version, env):
        raise NotImplementedError

    def start(self, version, env):
        """Start the UUT fresh (used by force mode)"""
        raise NotImplementedError

    def handle(self, version, env):
        """The object scripts use to reach this UUT, bound to its name.

        Scripts call its methods with the dot form, e.g. (.mode demo).
        None means scripts get no handle.
        """
        return None


def _registry(base):
    from . import block  # noqa: F401  importing it loads every plugin

    found = {}
    stack = list(base.__subclasses__())
    while stack:
        cls = stack.pop()
        stack.extend(cls.__subclasses__())
        if cls.name:
            found[cls.name] = cls
    return found


def uut_types():
    """name -> UUT class for every loaded plugin"""
    return _registry(UUT)


def environment_types():
    """name -> Environment class for every loaded plugin"""
    return _registry(Environment)
