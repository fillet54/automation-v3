"""Running jobs in-process, without a server or HTTP

LocalServer gives a Worker the job API straight from a queue database
and a reports directory. run_locally uses it with a throwaway in-memory
queue to run scripts on this machine, writing an ordinary report.
"""

from ...framework.planning import build_plan
from .. import jobs
from ..database import connect, init_db
from .host import Host
from .worker import Worker


class LocalServer:
    def __init__(self, conn, root, worker_url="local"):
        self.conn = conn
        self.root = root
        self.worker_url = worker_url

    def check_in(self, status, capabilities, started=False):
        jobs.check_in(self.conn, self.root, self.worker_url, status,
                      started=started, **capabilities)
        return True

    def pending_jobs(self):
        return [
            jobs.job_json(job)
            for job in jobs.available_jobs(self.conn, self.root, self.worker_url)
        ]

    def claim(self, job_id):
        return jobs.claim_job(self.conn, self.root, job_id, self.worker_url)

    def start(self, job_id):
        jobs.start_job(self.conn, self.root, job_id, self.worker_url)

    def release(self, job_id):
        jobs.release_job(self.conn, self.root, job_id, self.worker_url)

    def post_events(self, job_id, events):
        jobs.record_events(self.conn, self.root, job_id, self.worker_url, events)

    def complete(self, job_id, outcome, **details):
        jobs.complete_job(self.conn, self.root, job_id, self.worker_url, outcome,
                          **details)


def run_locally(root, scripts, reports_root, host=None, environments=None,
                variations=None, filter_source="", versions=None, observers=()):
    """Run scripts (paths relative to `root`) on this machine.

    Environments default to those `host` hosts; `variations` is None (all)
    or a set of "script::name" keys. Returns (report_id, plan). Raises
    jobs.QueueError if nothing can run.
    """
    host = host or Host()
    if environments is None:
        environments = list(host.environments)
    plan = build_plan("", root, scripts, environments=environments,
                      versions=versions, variations=variations,
                      filter_source=filter_source)

    conn = connect(":memory:")
    init_db(conn)
    report_id, _ = jobs.queue_plan(conn, reports_root, plan)
    worker = Worker(LocalServer(conn, reports_root), host, observers)
    worker.check_in(started=True)
    worker.work_until_idle()
    conn.close()
    return report_id, plan
