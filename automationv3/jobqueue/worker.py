"""Worker: pulls jobs from the central server and executes them

A worker hosts the environments named in its config file, e.g.::

    {"environments": {"sim": {"workdir": "/tmp/sim"}}}

and can install any UUT whose plugin is loaded. It only pulls jobs that
fit: the job's environment is hosted here and its UUTs are known.
"""

import json
import threading
import time
import traceback
from dataclasses import asdict

import requests
from flask import Flask, jsonify

from ..framework.executor import execute_closure
from ..framework.uut import Version, environment_types, uut_types
from ..reports.store import now_iso

app = Flask(__name__)

worker_status = "available"

# Seconds between polls for work while idle
POLL_INTERVAL = 2


class Host:
    """The environments this worker hosts and the UUTs it can install"""

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


class ServerClient:
    """The central server's job API, as seen by one worker"""

    def __init__(self, server_url, worker_url, host=None, session=None):
        self.server_url = server_url.rstrip("/")
        self.worker_url = worker_url
        self.host = host or Host()
        self.session = session or requests.Session()

    def _post(self, path, **data):
        return self.session.post(
            f"{self.server_url}/runner{path}",
            json={"worker_url": self.worker_url, **data},
        )

    def keepalive(self, status, started=False):
        return self.session.post(
            f"{self.server_url}/runner/workers",
            json={
                "url": self.worker_url,
                "status": status,
                "started": started,
                **self.host.capabilities(),
            },
        )

    def pending_jobs(self):
        """Pending jobs this worker can run, oldest first"""
        response = self.session.get(
            f"{self.server_url}/runner/jobs?worker_url={self.worker_url}"
        )
        response.raise_for_status()
        return response.json()

    def claim(self, job_id):
        """The claimed job with its closure, or None if someone else got it"""
        response = self._post(f"/jobs/{job_id}/claim")
        return response.json() if response.status_code == 200 else None

    def start(self, job_id):
        self._post(f"/jobs/{job_id}/start")

    def release(self, job_id):
        self._post(f"/jobs/{job_id}/release")

    def post_events(self, job_id, events):
        self._post(f"/jobs/{job_id}/events", events=events)

    def complete(self, job_id, outcome, **details):
        self._post(f"/jobs/{job_id}/complete", outcome=outcome, **details)


class ReportObserver:
    """Streams executor events to the server as they happen"""

    def __init__(self, client, job_id):
        self.client = client
        self.job_id = job_id
        self.seq = 0

    def _send(self, kind, **payload):
        self.seq += 1
        event = {"seq": self.seq, "ts": now_iso(), "kind": kind, **payload}
        self.client.post_events(self.job_id, [event])

    def on_procedure_begin(self, **kw):
        self._send("procedure_begin", **kw)

    def on_comment(self, **kw):
        self._send("comment", **kw)

    def on_step_start(self, **kw):
        self._send("step_start", **kw)

    def on_step_end(self, **kw):
        self._send("step_end", **kw)

    def on_procedure_end(self, **kw):
        self._send("procedure_end", **kw)


def install_uuts(host, job):
    """Install each requested UUT version unless it is already installed.

    Returns what is installed afterwards: uut -> {id, digest, action}.
    """
    env = host.environments.get(job["environment"])
    installed = {}
    for name, wanted in job["uut_versions"].items():
        uut = host.uuts[name]
        version = Version(**wanted)
        action = "kept"
        if uut.installed_version(env) != version:
            uut.install(version, env)
            action = "installed"
        if uut.installed_version(env) != version:
            raise RuntimeError(f"{name} {version.id} did not install")
        installed[name] = {**asdict(version), "action": action}
    return installed


def versions_installed(host, job):
    """True if every UUT the job needs is already at the right version"""
    env = host.environments.get(job["environment"])
    return all(
        host.uuts[name].installed_version(env) == Version(**wanted)
        for name, wanted in job["uut_versions"].items()
    )


def handles(host, job):
    """name -> handle for each of the job's UUTs that offers one"""
    env = host.environments.get(job["environment"])
    found = {}
    for name, wanted in job["uut_versions"].items():
        handle = host.uuts[name].handle(Version(**wanted), env)
        if handle is not None:
            found[name] = handle
    return found


def run_job(client, job, mode="force"):
    """Run a claimed job and report it.

    "probe" mode (precondition mode) runs the script against the
    environment as it is. If the UUT versions aren't installed, or a
    precondition fails, the job is released back to the queue and
    "released" is returned. "force" mode installs the UUTs, starts them
    fresh and runs the script; a failing precondition then makes the run
    "blocked".
    """
    host = client.host
    if mode == "probe" and not versions_installed(host, job):
        client.release(job["id"])
        return "released"

    client.start(job["id"])
    observer = ReportObserver(client, job["id"])
    details = {"mode": "precondition" if mode == "probe" else "force"}
    env = host.environments.get(job["environment"])
    if env is not None:
        details["fingerprint"] = env.fingerprint()
    try:
        if mode == "force":
            details["installed"] = install_uuts(host, job)
            for name, wanted in job["uut_versions"].items():
                host.uuts[name].start(Version(**wanted), env)
        else:
            details["installed"] = {
                name: {**wanted, "action": "kept"}
                for name, wanted in job["uut_versions"].items()
            }
        outcome = execute_closure(
            job["closure"],
            job["load_order"],
            observer,
            job.get("imports", ()),
            job.get("variation"),
            bindings=handles(host, job),
            mode=mode,
        )
    except Exception:
        observer._send("error", traceback=traceback.format_exc())
        outcome = "error"

    if outcome == "released":
        client.release(job["id"])
    else:
        client.complete(job["id"], outcome, **details)
    return outcome


def update_status(client, new_status):
    global worker_status
    worker_status = new_status
    client.keepalive(worker_status)


def run_claimed(client, job, mode):
    update_status(client, "busy")
    print("Running", job["script"], job["id"], mode)
    outcome = run_job(client, job, mode)
    print("Finished", job["id"], outcome)
    update_status(client, "available")
    return outcome


def work_once(client):
    """Run one job. Returns its outcome, or None if there was no work.

    Every compatible pending job is probed, oldest first; the first whose
    preconditions already hold (or heal) runs. If none does, the oldest
    compatible job runs in force mode.
    """
    for pending in client.pending_jobs():
        job = client.claim(pending["id"])
        if job is None:
            continue
        outcome = run_claimed(client, job, "probe")
        if outcome != "released":
            return outcome

    for pending in client.pending_jobs():
        job = client.claim(pending["id"])
        if job is not None:
            return run_claimed(client, job, "force")
    return None


def work_forever(client):
    while True:
        try:
            if work_once(client) is not None:
                continue  # look for more work straight away
        except requests.RequestException as e:
            print("Server unreachable:", e)
        time.sleep(POLL_INTERVAL)


def keepalive_forever(client):
    while True:
        time.sleep(60)
        try:
            client.keepalive(worker_status)
        except requests.RequestException as e:
            print("Keepalive failed:", e)


def start_worker_threads():
    client = ServerClient(
        app.config["SERVER_URL"],
        app.config["SELF_URL"],
        host=Host.from_file(app.config.get("CONFIG_PATH")),
    )
    response = client.keepalive(worker_status, started=True)
    if response.status_code == 200:
        print("Registration successful")
    for target in (keepalive_forever, work_forever):
        threading.Thread(target=target, args=(client,), daemon=True).start()


@app.route("/")
def index():
    return jsonify({"status": worker_status})
