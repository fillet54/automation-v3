"""Workers: pull jobs, run them, report back

A Worker takes jobs from a server, which is anything with this
interface (the HTTP client, or an in-process LocalServer)::

    check_in(status, capabilities, started=False) -> bool
    pending_jobs() -> [job]          jobs this worker can run, oldest first
    claim(job_id) -> job | None      the job with its closure, if claimed
    start(job_id), release(job_id)
    post_events(job_id, events)
    complete(job_id, outcome, **details)

Scheduling is warm-first: every pending job is probed against the
environment as it is, and the first whose preconditions hold (or heal)
runs. If none does, the oldest runs in force mode with its UUTs
installed and started fresh.
"""

import threading
import time
import traceback
from dataclasses import asdict

from ...framework.executor import execute_closure
from ...framework.observer import ObserverManager
from ...framework.uut import Version
from ..reports.store import now_iso

# Seconds between polls for work while idle, and between keepalives
POLL_INTERVAL = 2
KEEPALIVE_INTERVAL = 60


class ReportObserver:
    """Streams executor events to the server as they happen"""

    def __init__(self, server, job_id):
        self.server = server
        self.job_id = job_id
        self.seq = 0

    def send(self, kind, **payload):
        self.seq += 1
        event = {"seq": self.seq, "ts": now_iso(), "kind": kind, **payload}
        self.server.post_events(self.job_id, [event])

    def on_procedure_begin(self, **kw):
        self.send("procedure_begin", **kw)

    def on_comment(self, **kw):
        self.send("comment", **kw)

    def on_step_start(self, **kw):
        self.send("step_start", **kw)

    def on_step_end(self, **kw):
        self.send("step_end", **kw)

    def on_phase_start(self, **kw):
        self.send("phase_start", **kw)

    def on_phase_end(self, **kw):
        self.send("phase_end", **kw)

    def on_call_start(self, **kw):
        self.send("call_start", **kw)

    def on_attach(self, name, data, index=None, **kw):
        stored = self.server.attach(self.job_id, name, data)
        self.send("attachment", name=stored, index=index, size=len(data), **kw)

    def on_table_start(self, **kw):
        self.send("table_start", **kw)

    def on_row_start(self, **kw):
        self.send("row_start", **kw)

    def on_row_end(self, **kw):
        self.send("row_end", **kw)

    def on_call_end(self, **kw):
        self.send("call_end", **kw)

    def on_connector(self, **kw):
        self.send("connector", **kw)

    def on_cleanup(self, **kw):
        self.send("cleanup", **kw)

    def on_procedure_end(self, **kw):
        self.send("procedure_end", **kw)

    def on_error(self, **kw):
        self.send("error", **kw)


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


class Worker:
    def __init__(self, server, host, observers=()):
        self.server = server
        self.host = host
        self.status = "available"
        # Extra observers (e.g. console output) see every job's events
        self.observers = list(observers)

    def check_in(self, started=False):
        return self.server.check_in(self.status, self.host.capabilities(), started)

    def set_status(self, status):
        self.status = status
        self.check_in()

    def run_job(self, job, mode="force"):
        """Run a claimed job and report it.

        "probe" mode (precondition mode) runs the script against the
        environment as it is. If the UUT versions aren't installed, or a
        precondition fails, the job is released back to the queue and
        "released" is returned. "force" mode installs the UUTs, starts
        them fresh and runs the script; a failing precondition then makes
        the run "blocked".
        """
        server, host = self.server, self.host
        if mode == "probe" and not versions_installed(host, job):
            server.release(job["id"])
            return "released"

        server.start(job["id"])
        observer = ObserverManager()
        for each in (ReportObserver(server, job["id"]), *self.observers):
            observer.add_observer(each)
        details = {"mode": "precondition" if mode == "probe" else "force"}
        observer.on_job(
            script=job["script"],
            environment=job["environment"],
            variation=job.get("variation"),
            mode=details["mode"],
        )
        env = host.environments.get(job["environment"])
        if env is not None:
            details["fingerprint"] = host.fingerprint(job["environment"])
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
            observer.on_error(traceback=traceback.format_exc())
            outcome = "error"

        if outcome == "released":
            server.release(job["id"])
        else:
            server.complete(job["id"], outcome, **details)
        return outcome

    def run_claimed(self, job, mode):
        self.set_status("busy")
        outcome = self.run_job(job, mode)
        self.set_status("available")
        return outcome

    def work_once(self):
        """Run one job. Returns its outcome, or None if there was no work."""
        for pending in self.server.pending_jobs():
            job = self.server.claim(pending["id"])
            if job is None:
                continue
            outcome = self.run_claimed(job, "probe")
            if outcome != "released":
                return outcome

        for pending in self.server.pending_jobs():
            job = self.server.claim(pending["id"])
            if job is not None:
                return self.run_claimed(job, "force")
        return None

    def work_until_idle(self):
        """Run jobs until none is left. Returns their outcomes."""
        outcomes = []
        while (outcome := self.work_once()) is not None:
            outcomes.append(outcome)
        return outcomes

    def work_forever(self):
        while True:
            try:
                if self.work_once() is not None:
                    continue  # look for more work straight away
            except Exception as e:  # e.g. the server is unreachable
                print("Worker error:", e)
            time.sleep(POLL_INTERVAL)

    def keepalive_forever(self):
        while True:
            time.sleep(KEEPALIVE_INTERVAL)
            try:
                self.check_in()
            except Exception as e:
                print("Keepalive failed:", e)

    def start(self):
        """Register with the server, then work and send keepalives in the
        background. Returns the threads."""
        self.check_in(started=True)
        threads = [
            threading.Thread(target=target, daemon=True)
            for target in (self.keepalive_forever, self.work_forever)
        ]
        for thread in threads:
            thread.start()
        return threads
