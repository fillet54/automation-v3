"""The local client's side of a central server: its API, and credentials

`automation-v3 login` signs this machine in: the server emails a link,
and once it is approved the client keeps a device token in
credentials.json (only readable by you) under the config folder,
~/.config/automation-v3 (or $AUTOMATION_CONFIG_HOME, or
$XDG_CONFIG_HOME/automation-v3).

CentralClient wraps the server's /api (see web/api.py).
"""

import json
import os
import socket
import subprocess
import time
from pathlib import Path

import requests

from ..framework.closure import resolve


class ClientError(Exception):
    pass


def config_home():
    if os.environ.get("AUTOMATION_CONFIG_HOME"):
        return Path(os.environ["AUTOMATION_CONFIG_HOME"])
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "automation-v3"


def normal_server(url):
    url = (url or "").strip().rstrip("/")
    if url and "://" not in url:
        url = f"http://{url}"
    return url


# Credentials: {"default": url, "servers": {url: {"token", "email"}}}


def credentials_path():
    return config_home() / "credentials.json"


def load_credentials():
    path = credentials_path()
    if not path.is_file():
        return {"default": None, "servers": {}}
    return json.loads(path.read_text())


def save_credentials(data):
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def remember(server, token, email):
    data = load_credentials()
    data["servers"][server] = {"token": token, "email": email}
    data["default"] = server
    save_credentials(data)


def forget(server):
    data = load_credentials()
    data["servers"].pop(server, None)
    if data.get("default") == server:
        data["default"] = next(iter(data["servers"]), None)
    save_credentials(data)


def signed_in(server=None):
    """(server, token, email) for `server`, or the default one. Raises
    ClientError if this machine isn't signed in to it."""
    data = load_credentials()
    server = normal_server(server) or data.get("default")
    if not server:
        raise ClientError("Not signed in: run automation-v3 login --server URL")
    found = data["servers"].get(server)
    if not found:
        raise ClientError(f"Not signed in to {server}: run automation-v3 login --server {server}")
    return server, found["token"], found.get("email")


def device_name():
    return socket.gethostname()


class CentralClient:
    def __init__(self, server, token=None, session=None):
        self.server = normal_server(server)
        self.token = token
        self.session = session or requests.Session()

    @classmethod
    def signed_in(cls, server=None, session=None):
        server, token, _ = signed_in(server)
        return cls(server, token, session)

    def headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def call(self, method, path, json=None, params=None, ok=(200, 201)):
        url = f"{self.server}/api{path}"
        try:
            if method == "GET":
                response = self.session.get(url, headers=self.headers(), params=params)
            else:
                response = self.session.post(url, json=json, headers=self.headers())
        except requests.RequestException as e:
            raise ClientError(f"Can't reach {self.server}: {e}") from None
        if response.status_code == 401:
            raise ClientError(f"{self.server} doesn't know this machine any more: "
                              f"run automation-v3 login --server {self.server}")
        if response.status_code not in ok:
            try:
                data = response.json() or {}
            except ValueError:
                data = {}
            message = data.get("error") or "; ".join(data.get("errors", [])) \
                or f"HTTP {response.status_code}"
            raise ClientError(message)
        return response

    # Signing in

    def login(self, email, device=None, wait=None, say=print):
        """Sign this machine in as `email`: the server emails a link; once it
        is approved, the token is remembered. Returns the email."""
        device = device or device_name()
        wait = wait or time.sleep
        started = self.call("POST", "/login/start", {"email": email, "device": device}).json()
        say(f"We emailed {email} a link. Open it and approve {device} "
            f"(it works for {started['expires_in'] // 60} minutes).")
        deadline = started["expires_in"]
        waited = 0
        while waited <= deadline:
            response = self.call("POST", "/login/poll", {"code": started["code"]},
                                 ok=(200, 202))
            if response.status_code == 200:
                got = response.json()
                remember(self.server, got["token"], got["email"])
                self.token = got["token"]
                return got["email"]
            wait(started["interval"])
            waited += started["interval"]
        raise ClientError("The link expired before it was approved: try again")

    def logout(self):
        try:
            self.call("POST", "/logout", {})
        finally:
            forget(self.server)

    # What the server knows

    def whoami(self):
        return self.call("GET", "/whoami").json()

    def requirements(self, ids, context=None):
        params = [("id", id) for id in ids] + ([("context", context)] if context else [])
        return self.call("GET", "/requirements", params=params).json()

    def uuts(self):
        return self.call("GET", "/uuts").json()

    def environments(self):
        return self.call("GET", "/environments").json()

    # Scratch runs

    def scratch(self, workspace, files, scripts, environment=None, variation=None,
                uut_versions=None, device=None):
        response = self.call("POST", "/scratch", {
            "workspace": workspace, "files": files, "scripts": scripts,
            "environment": environment, "variation": variation,
            "uut_versions": uut_versions or {}, "device": device or device_name()})
        return response.json()["runs"]

    def run(self, run_id):
        return self.call("GET", f"/scratch/{run_id}").json()

    def events(self, run_id, after=0):
        return self.call("GET", f"/scratch/{run_id}/events", params={"after": after}).json()

    def follow(self, run_id, on_event=None, wait=None, interval=1):
        """Wait for a run to finish, passing each event to `on_event`.
        Returns its outcome."""
        wait = wait or time.sleep
        seen = 0
        while True:
            got = self.events(run_id, seen)
            for event in got["events"]:
                if on_event:
                    on_event(event)
            seen += len(got["events"])
            if got["finished"]:
                return got["outcome"]
            wait(interval)


def upload_files(root, scripts):
    """The files to upload to run `scripts` (relative to `root`): each
    one's closure, merged. Raises ClientError with what's wrong with any."""
    files, errors = {}, []
    for script in scripts:
        try:
            closure = resolve(root, script)
        except FileNotFoundError:
            errors.append(f"{script}: no such script under {root}")
            continue
        errors += [f"{script}: {e}" for e in closure.errors]
        files.update(closure.files)
    if errors:
        raise ClientError("\n".join(errors))
    return files


def current_branch(root):
    """The git branch checked out at `root`, or "" """
    try:
        out = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root,
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def replay(observer, event):
    """Show a server-side event through an executor observer (as the
    console shows a local run)"""
    payload = {k: v for k, v in event.items() if k not in ("seq", "ts", "kind")}
    method = getattr(observer, f"on_{event['kind']}", None)
    if method is not None:
        try:
            method(**payload)
        except TypeError:
            pass
