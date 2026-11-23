"""Workers: pull jobs, run them, report back

A Worker takes jobs from a server, which is anything with this
interface (the HTTP client, or an in-process LocalServer)::

    check_in(status, capabilities, started=False) -> bool
    pending_jobs() -> [job]          jobs this worker can run, scratch
                                     runs first, then oldest first
    claim(job_id) -> job | None      the job with its closure, if claimed
    start(job_id), release(job_id)
    post_events(job_id, events)
    complete(job_id, outcome, **details)

Those taking a job_id raise JobLost when the server no longer has this
worker holding the job (it was reaped, rerun or deleted): the worker
stops working on it, and the job's outcome is LOST. Any other failure
to post events keeps them to send again; completing is retried.

Scheduling is warm-first: every pending job is probed against the
environment as it is, and the first whose preconditions hold (or heal)
runs. If none does, the first (a scratch run, else the oldest) runs in
force mode with its UUTs installed and started fresh.

The console (kernel.py) borrows a worker in this process: borrow()
waits for the job running, if any, then the worker takes no jobs, with
status "console", until give_back().
"""

import threading
import time
import traceback
from dataclasses import asdict

from ...framework.executor import execute_closure
from ...framework.observer import ObserverManager
from ...framework.uut import Version
from ..util import now_iso

# Seconds between polls for work while idle, and between keepalives
POLL_INTERVAL = 2
KEEPALIVE_INTERVAL = 60
# Seconds to wait before each retry of finishing a job
RETRY_DELAYS = (1, 2, 5)

LOST = "lost"  # the outcome of a job the server took back while it ran


class JobLost(Exception):
    """The server no longer has this worker holding the job"""

    def __init__(self, job_id, reason=""):
        super().__init__(f"job {job_id} is no longer this worker's"
                         + (f": {reason}" if reason else ""))
        self.job_id = job_id


class ReportObserver:
    """Streams executor events to the server as they happen"""

    def __init__(self, server, job_id):
        self.server = server
        self.job_id = job_id
        self.seq = 0
        self.unsent = []  # events the server hasn't taken yet, in order
        self.lost = None  # the JobLost, once the server has taken the job back

    def send(self, kind, **payload):
        self.seq += 1
        self.unsent.append({"seq": self.seq, "ts": now_iso(), "kind": kind, **payload})
        self.flush(required=False)

    def flush(self, required=True):
        """Send the events not sent yet. A failure other than JobLost
        keeps them for the next try, raised only if `required`."""
        if self.lost is not None:
            raise self.lost
        if not self.unsent:
            return
        try:
            self.server.post_events(self.job_id, list(self.unsent))
        except JobLost as e:
            self.lost = e
            raise
        except Exception as e:  # e.g. unreachable for a moment
            if required:
                raise
            print(f"Job {self.job_id}: couldn't send events (will retry): {e}")
            return
        self.unsent.clear()

    def on_procedure_begin(self, **kw):
        self.send("procedure_begin", **kw)

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
        if self.lost is not None:
            raise self.lost
        try:
            stored = self.server.attach(self.job_id, name, data)
        except JobLost as e:  # kept, so the run stops at its next event
            self.lost = e
            raise
        self.send("attachment", name=stored, index=index, size=len(data), **kw)

    def on_table_start(self, **kw):
        self.send("table_start", **kw)

    def on_row_start(self, **kw):
        self.send("row_start", **kw)

    def on_row_end(self, **kw):
        self.send("row_end", **kw)

    def on_call_end(self, **kw):
        self.send("call_end", **kw)

    def on_ref(self, **kw):
        self.send("ref", **kw)

    def on_cleanup(self, **kw):
        self.send("cleanup", **kw)

    def on_procedure_end(self, **kw):
        self.send("procedure_end", **kw)

    def on_error(self, **kw):
        self.send("error", **kw)


def _job_versions(job):
    return {name: Version(**wanted) for name, wanted in job["uut_versions"].items()}


def install_uuts(host, environment, uut_versions):
    """Install each requested UUT version unless it is already installed.

    Returns what is installed afterwards: uut -> {id, digest, action}.
    """
    env = host.environments.get(environment)
    installed = {}
    for name, version in uut_versions.items():
        uut = host.uuts[name]
        action = "kept"
        if uut.installed_version(env) != version:
            uut.install(version, env)
            action = "installed"
        if uut.installed_version(env) != version:
            raise RuntimeError(f"{name} {version.id} did not install")
        installed[name] = {**asdict(version), "action": action}
    return installed


def versions_installed(host, environment, uut_versions):
    """True if every UUT is already at the right version"""
    env = host.environments.get(environment)
    return all(
        host.uuts[name].installed_version(env) == version
        for name, version in uut_versions.items()
    )


def handles(host, environment, uut_versions):
    """name -> handle for each UUT that offers one"""
    env = host.environments.get(environment)
    found = {}
    for name, version in uut_versions.items():
        handle = host.uuts[name].handle(version, env)
        if handle is not None:
            found[name] = handle
    return found


class Worker:
    def __init__(self, server, host, observers=()):
        self.server = server
        self.host = host
        self.status = "available"
        self.lock = threading.Lock()  # held while looking for or running a job
        self.borrowed = False
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
        the run "blocked". LOST if the server took the job back.
        """
        server, host = self.server, self.host
        environment = job["environment"]
        uut_versions = _job_versions(job)
        if mode == "probe" and not versions_installed(host, environment, uut_versions):
            try:
                server.release(job["id"])
            except JobLost:
                return LOST
            return "released"

        try:
            server.start(job["id"])
        except JobLost:
            return LOST
        except Exception:
            self.give_up(job["id"])  # don't leave it claimed: queue it again
            raise
        report = ReportObserver(server, job["id"])
        observer = ObserverManager()
        for each in (report, *self.observers):
            observer.add_observer(each)
        details = {"mode": "precondition" if mode == "probe" else "force"}
        try:
            outcome = self.execute(job, mode, observer, details)
            if report.lost is not None:  # an observer's JobLost the run swallowed
                return LOST
            self.finish(job["id"], report, outcome, details)
        except JobLost:
            return LOST
        return outcome

    def execute(self, job, mode, observer, details):
        """Run the job's script; its outcome ("error" if it raised). A
        JobLost from the observers is raised: the run is abandoned."""
        host, environment = self.host, job["environment"]
        uut_versions = _job_versions(job)
        observer.on_job(
            script=job["script"],
            environment=environment,
            variation=job.get("variation"),
            mode=details["mode"],
        )
        env = host.environments.get(environment)
        if env is not None:
            details["fingerprint"] = host.fingerprint(environment)
        try:
            if mode == "force":
                details["installed"] = install_uuts(host, environment, uut_versions)
                for name, version in uut_versions.items():
                    host.uuts[name].start(version, env)
            else:
                details["installed"] = {
                    name: {**wanted, "action": "kept"}
                    for name, wanted in job["uut_versions"].items()
                }
            bound = handles(host, environment, uut_versions)
            return execute_closure(
                job["closure"],
                job["load_order"],
                observer,
                job.get("imports", ()),
                job.get("variation"),
                bindings=bound,
                mode=mode,
                clock=env.clock(bound) if env is not None else None,
            )
        except JobLost:
            raise
        except Exception:
            observer.on_error(traceback=traceback.format_exc())
            return "error"

    def finish(self, job_id, report, outcome, details):
        """Send the events left, then release or complete the job,
        retrying (see RETRY_DELAYS) while the server can't be reached"""
        def done():
            report.flush()
            if outcome == "released":
                self.server.release(job_id)
            else:
                self.server.complete(job_id, outcome, **details)

        for delay in RETRY_DELAYS:
            try:
                return done()
            except JobLost:
                raise
            except Exception as e:
                print(f"Job {job_id}: couldn't report {outcome} (retrying): {e}")
                time.sleep(delay)
        return done()

    def give_up(self, job_id):
        """Hand a job back to the queue, if the server will take it"""
        try:
            self.server.release(job_id)
        except Exception as e:
            print(f"Job {job_id}: couldn't release it: {e}")

    def run_claimed(self, job, mode):
        self.set_status("busy")
        try:
            return self.run_job(job, mode)
        finally:
            self.set_status("available")

    def borrow(self, timeout=60):
        """Take the worker off the queue (for the console): waits for the
        job it is running. True if it is now borrowed, False if the job
        didn't finish within `timeout` seconds."""
        if not self.lock.acquire(timeout=timeout):
            return False
        try:
            self.borrowed = True
            self.set_status("console")
        finally:
            self.lock.release()
        return True

    def give_back(self):
        """Put the worker back on the queue"""
        with self.lock:
            self.borrowed = False
            self.set_status("available")

    def work_once(self):
        """Run one job. Returns its outcome, or None if there was no work
        (or the worker is borrowed)."""
        with self.lock:
            if self.borrowed:
                return None
            return self._work_once()

    def _work_once(self):
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
