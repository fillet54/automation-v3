"""Units under test and the environments they run in

Both are extension points. Plugins in `automationv3.plugins` subclass
`UUT` or `Environment` and set `name`; tests declare which they need
with `(uut :name)` and `(environments :name ...)`.

The server calls `UUT.list_versions` to offer versions when queuing.
Workers host Environment instances (configured per worker) and call
`installed_version` / `install` before running a job.

Builds live in a build repository of the plugin's own (automation-v3
never stores them; installers pull from it). The local client finds a
build someone made on their machine with `find_local_build` and puts it in
the repository with `upload_build`, using their own credentials; after
that, `list_versions` everywhere offers it like any other version.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Version:
    """A UUT version. The digest identifies the exact bits."""

    id: str
    digest: str


@dataclass(frozen=True)
class LocalBuild:
    """A build on this machine, not necessarily uploaded yet. `digest`
    identifies the exact bits, as Version.digest does once it's uploaded;
    `id` is the version id it would be uploaded as; `built` its time
    (seconds since the epoch)."""

    uut: str
    path: Path
    id: str
    digest: str
    built: float = 0.0


class Environment:
    """A runtime target hosted by a worker, e.g. a simulator or a bench"""

    name = None

    def __init__(self, **params):
        self.params = params

    def fingerprint(self):
        """Facts about this environment that can affect results"""
        return {}

    def clock(self, handles):
        """The clock runs here keep time by (see framework/clock.py), given
        the run's UUT handles (name -> handle). None: the wall clock."""
        return None


class UUT:
    """A unit under test that can be installed into an environment"""

    name = None

    def list_versions(self):
        """Every installable Version, oldest first"""
        return []

    def find_version(self, id, versions=None):
        return next((v for v in (versions if versions is not None
                                 else self.list_versions()) if v.id == id), None)

    def report_versions(self):
        """The versions a report may run on, oldest first: by default every
        listed one. A plugin whose build repository also holds builds people
        uploaded from their machines (see upload_build) leaves those out:
        they are for scratch runs only."""
        return self.list_versions()

    def find_local_build(self, path):
        """The newest build in the folder `path` (where this UUT's builds
        land on a developer's machine), as a LocalBuild; None if there is
        none, or this UUT has no local builds"""
        return None

    def upload_build(self, build):
        """Put a LocalBuild in the build repository, with the credentials of
        whoever is running this, and return its Version. Only called for a
        build whose digest no listed version has."""
        raise NotImplementedError(f"{self.name} builds can't be uploaded")

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
    from .plugins import load_plugins
    load_plugins()

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
