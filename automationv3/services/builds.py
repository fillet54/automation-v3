"""Local builds, as the local client sees them

Where each UUT's builds land on this machine is set once in the client's
config, client.json in the config folder (see services/client.py)::

    {"builds": {"lm": "~/work/luminary/build"}}

For each UUT a script uses, the client asks its plugin for the newest build
there and compares it with the versions the central server lists: if no
version has its digest it hasn't been uploaded yet, and the client offers
to upload it (the plugin pushes it to the build repository with your own
credentials) or to keep using the version you used last.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from ..framework.uut import uut_types
from .client import config_home

UPLOAD = "upload"  # the version choice meaning: upload the local build, use it


def client_config():
    path = config_home() / "client.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except ValueError as e:
        raise ValueError(f"{path} isn't valid JSON: {e}") from None


def build_folders(config=None):
    """uut -> the folder its local builds land in"""
    config = client_config() if config is None else config
    return {uut: Path(folder).expanduser() for uut, folder in (config.get("builds") or {}).items()}


def find_local_build(uut, config=None):
    """The newest local build of `uut`, or None"""
    folder = build_folders(config).get(uut)
    cls = uut_types().get(uut)
    if folder is None or cls is None or not folder.is_dir():
        return None
    return cls().find_local_build(folder)


# The version used last, per UUT: state.json in the config folder


def state_path():
    return config_home() / "state.json"


def last_used(uut):
    path = state_path()
    try:
        return json.loads(path.read_text()).get("last_used", {}).get(uut)
    except (OSError, ValueError):
        return None


def remember_used(versions):
    """Remember `versions` (uut -> version id) as the ones used last"""
    path = state_path()
    try:
        state = json.loads(path.read_text())
    except (OSError, ValueError):
        state = {}
    state.setdefault("last_used", {}).update(versions)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


@dataclass
class BuildChoice:
    """What to offer for one UUT when running in scratch"""

    uut: str
    options: list  # [(value, label)]
    selected: str
    build: object = None  # the LocalBuild, if any
    uploaded_as: str = None  # the version id it is already uploaded as

    @property
    def needs_upload(self):
        return self.build is not None and self.uploaded_as is None


def choices(uuts, server_versions, config=None):
    """A BuildChoice for each of `uuts`, given the server's versions
    (uut -> [{id, digest}], oldest first). The options are: upload the
    local build (when there's one not uploaded yet), then the server's
    versions, newest first. The default is the local build once it's
    uploaded, else the version used last, else the newest."""
    out = []
    for uut in uuts:
        versions = list(reversed(server_versions.get(uut, [])))
        build = find_local_build(uut, config)
        uploaded = next((v["id"] for v in versions if build and v["digest"] == build.digest),
                        None)
        previous = last_used(uut)
        ids = [v["id"] for v in versions]

        def label(id):
            notes = [n for n, yes in (("your local build", id == uploaded),
                                      ("last used", id == previous)) if yes]
            return id + (f" ({', '.join(notes)})" if notes else "")

        options = [(id, label(id)) for id in ids]
        if build is not None and uploaded is None:
            options.insert(0, (UPLOAD, f"upload your local build ({build.id})"))
        selected = uploaded or (previous if previous in ids else None) \
            or (ids[0] if ids else (UPLOAD if options else ""))
        out.append(BuildChoice(uut, options, selected, build, uploaded))
    return out


def resolve_versions(chosen, config=None, upload=None):
    """uut -> version id, uploading the local build for any chosen as
    UPLOAD (with `upload(build) -> Version`, default the plugin's)"""
    resolved = {}
    for uut, value in chosen.items():
        if value != UPLOAD:
            resolved[uut] = value
            continue
        build = find_local_build(uut, config)
        if build is None:
            raise ValueError(f"There's no local {uut} build to upload")
        version = (upload or uut_types()[uut]().upload_build)(build)
        resolved[uut] = version.id
    return resolved
