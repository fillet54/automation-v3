import json
import shutil
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask

import automationv3
from automationv3.database import close_db, connect, init_db
from automationv3.framework.executor import execute_script
from automationv3.jobqueue import models, worker
from automationv3.jobqueue.views import jobqueue
from automationv3.reports import store
from automationv3.reports.views import reports

PASSING = '''
"
=====
Title
=====
"
(Wait 1)
(Wait 2)
'''

FAILING = '''
"Docs"
(Wait 1)
(Verify X)
(Wait 2)
'''


class Recorder:
    def __init__(self):
        self.events = []

    def __getattr__(self, name):
        return lambda **kw: self.events.append((name[3:], kw))


class TestUuid7(unittest.TestCase):
    def test_version_and_order(self):
        ids = [store.uuid7() for _ in range(2000)]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(uuid.UUID(ids[0]).version, 7)


class TestStore(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_report_and_runs(self):
        report_id = store.create_report(self.root, scripts=["a.rvt"])
        first = store.create_run(self.root, report_id, "a.rvt", {"a.rvt": "(Wait 1)"})
        second = store.create_run(self.root, report_id, "a.rvt", {"a.rvt": "(Wait 2)"})

        self.assertEqual(store.load_report(self.root, report_id)["scripts"], ["a.rvt"])
        self.assertEqual([r["id"] for r in store.list_runs(self.root, report_id)],
                         [first, second])
        self.assertEqual(store.read_closure(self.root, report_id, first),
                         {"a.rvt": "(Wait 1)"})
        self.assertTrue(store.run_dir(self.root, report_id, first).joinpath("files").is_dir())

    def test_events_and_outcome(self):
        report_id = store.create_report(self.root)
        run_id = store.create_run(self.root, report_id, "a.rvt", {"a.rvt": ""})
        store.append_events(self.root, report_id, run_id, [{"seq": 1}, {"seq": 2}])
        store.append_events(self.root, report_id, run_id, [{"seq": 3}])
        self.assertEqual([e["seq"] for e in store.read_events(self.root, report_id, run_id)],
                         [1, 2, 3])

        store.update_run(self.root, report_id, run_id, outcome="pass")
        self.assertEqual(store.load_run(self.root, report_id, run_id)["outcome"], "pass")

    def test_closure_keeps_subdirectories(self):
        report_id = store.create_report(self.root)
        closure = {"core.rvt": "", "BRA/tc.rvt": "(Wait 1)"}
        run_id = store.create_run(self.root, report_id, "BRA/tc.rvt", closure)
        self.assertEqual(store.read_closure(self.root, report_id, run_id), closure)


class TestExecutor(unittest.TestCase):
    def test_passing_script(self):
        recorder = Recorder()
        self.assertEqual(execute_script(PASSING, recorder), "pass")
        kinds = [kind for kind, _ in recorder.events]
        self.assertEqual(kinds, ["procedure_begin", "comment",
                                 "step_start", "step_end",
                                 "step_start", "step_end",
                                 "procedure_end"])

    def test_failing_step_stops_script(self):
        recorder = Recorder()
        self.assertEqual(execute_script(FAILING, recorder), "fail")
        ends = [kw for kind, kw in recorder.events if kind == "step_end"]
        self.assertEqual([e["passed"] for e in ends], [True, False])
        self.assertIn("No BuildingBlock matches (Verify X)", ends[1]["stderr"])
        self.assertEqual([e["index"] for e in ends], [1, 2])
        self.assertEqual(recorder.events[-1], ("procedure_end", {"outcome": "fail"}))


class QueueTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "reports"
        self.root.mkdir()
        self.db_file = self.tmp / "test.db"
        self.conn = connect(self.db_file)
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp)


class TestJobModels(QueueTestCase):
    def test_claim_is_exclusive(self):
        _, run_id = models.queue_script(self.conn, self.root, "a.rvt", PASSING)
        self.assertTrue(models.claim(self.conn, run_id, "http://w1"))
        self.assertFalse(models.claim(self.conn, run_id, "http://w2"))
        self.assertEqual(models.find_jobs(self.conn, "pending"), [])

    def test_release_returns_job_to_queue(self):
        _, run_id = models.queue_script(self.conn, self.root, "a.rvt", PASSING)
        models.claim(self.conn, run_id, "http://w1")
        self.assertFalse(models.release(self.conn, run_id, "http://w2"))
        self.assertTrue(models.release(self.conn, run_id, "http://w1"))
        self.assertEqual([j.id for j in models.find_jobs(self.conn, "pending")], [run_id])

    def test_finish_writes_outcome_then_removes_job(self):
        report_id, run_id = models.queue_script(self.conn, self.root, "a.rvt", PASSING)
        models.claim(self.conn, run_id, "http://w1")
        models.finish(self.conn, self.root, models.get_job(self.conn, run_id), "pass")
        self.assertIsNone(models.get_job(self.conn, run_id))
        run = store.load_run(self.root, report_id, run_id)
        self.assertEqual(run["outcome"], "pass")
        self.assertEqual(run["worker"], "http://w1")

    def test_jobs_of_missing_workers_become_errors(self):
        models.save_worker(self.conn, "http://alive", "busy")
        models.save_worker(self.conn, "http://gone", "busy")
        _, alive_job = models.queue_script(self.conn, self.root, "a.rvt", PASSING)
        report_id, gone_job = models.queue_script(self.conn, self.root, "b.rvt", PASSING)
        models.claim(self.conn, alive_job, "http://alive")
        models.claim(self.conn, gone_job, "http://gone")

        # Only "alive" has sent a keepalive recently
        with self.conn:
            self.conn.execute(
                "UPDATE workers SET last_keepalive = ? WHERE url = 'http://gone'",
                ((datetime.utcnow() - timedelta(minutes=10)).isoformat(sep=" "),),
            )

        self.assertEqual(models.reap_lost_jobs(self.conn, self.root), {"http://gone"})
        self.assertIsNotNone(models.get_job(self.conn, alive_job))
        self.assertIsNone(models.get_job(self.conn, gone_job))
        self.assertEqual(store.load_run(self.root, report_id, gone_job)["outcome"], "error")

    def test_cleanup_finished_removes_stale_rows(self):
        report_id, run_id = models.queue_script(self.conn, self.root, "a.rvt", PASSING)
        # Simulate a crash after run.json was written but before the delete
        store.update_run(self.root, report_id, run_id, outcome="pass")
        models.cleanup_finished(self.conn, self.root)
        self.assertIsNone(models.get_job(self.conn, run_id))


class FlaskSession:
    """Lets the worker's ServerClient talk to a Flask test client"""

    def __init__(self, client, server_url):
        self.client = client
        self.server_url = server_url

    def get(self, url):
        return Response(self.client.get(url[len(self.server_url):]))

    def post(self, url, json=None):
        return Response(self.client.post(url[len(self.server_url):], json=json))


class Response:
    def __init__(self, response):
        self.status_code = response.status_code
        self._response = response

    def json(self):
        return self._response.get_json()

    def raise_for_status(self):
        assert self.status_code < 400, self.status_code


class TestWorkerAgainstServer(QueueTestCase):
    def setUp(self):
        super().setUp()
        app = Flask(__name__, template_folder=Path(automationv3.__file__).parent / "templates")
        app.register_blueprint(jobqueue, url_prefix="/runner")
        app.register_blueprint(reports, url_prefix="/reports")
        app.teardown_appcontext(close_db)
        app.config["DB_PATH"] = self.db_file
        app.config["REPORTS_PATH"] = self.root
        app.testing = True
        self.http = app.test_client()

        session = FlaskSession(self.http, "http://server")
        self.worker = worker.ServerClient("http://server", "http://w1", session=session)
        self.worker.keepalive("available", started=True)

    def queue(self, text, script="BRA/tc.rvt"):
        response = self.http.post("/runner/jobs", json={"script": script, "text": text})
        self.assertEqual(response.status_code, 201)
        return response.get_json()

    def test_worker_runs_queued_script(self):
        ids = self.queue(FAILING)
        self.assertEqual(worker.work_once(self.worker), "fail")
        self.assertIsNone(worker.work_once(self.worker))

        run = store.load_run(self.root, ids["report_id"], ids["run_id"])
        self.assertEqual(run["outcome"], "fail")
        self.assertIn("started", run)
        events = store.read_events(self.root, ids["report_id"], ids["run_id"])
        self.assertEqual(events[0]["kind"], "procedure_begin")
        self.assertEqual(events[-1], {**events[-1], "kind": "procedure_end", "outcome": "fail"})
        self.assertEqual([e["seq"] for e in events], list(range(1, len(events) + 1)))

        page = self.http.get(f"/reports/{ids['report_id']}/runs/{ids['run_id']}")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"No BuildingBlock matches (Verify X)", page.data)
        self.assertIn(b">pass<", page.data)
        self.assertIn(b">fail<", page.data)
        self.assertIn(b">not run<", page.data)

    def test_only_holder_can_report(self):
        ids = self.queue(PASSING)
        self.assertIsNotNone(self.worker.claim(ids["run_id"]))
        response = self.http.post(f"/runner/jobs/{ids['run_id']}/complete",
                                  json={"worker_url": "http://w2", "outcome": "pass"})
        self.assertEqual(response.status_code, 409)

    def test_restarted_worker_errors_its_jobs(self):
        ids = self.queue(PASSING)
        self.worker.claim(ids["run_id"])
        self.worker.keepalive("available", started=True)
        run = store.load_run(self.root, ids["report_id"], ids["run_id"])
        self.assertEqual(run["outcome"], "error")

    def test_rerun_adds_run_to_same_report(self):
        ids = self.queue(PASSING)
        worker.work_once(self.worker)
        response = self.http.post(f"/reports/{ids['report_id']}/runs/{ids['run_id']}/rerun")
        self.assertEqual(response.status_code, 302)

        runs = store.list_runs(self.root, ids["report_id"])
        self.assertEqual(len(runs), 2)
        self.assertEqual(store.read_closure(self.root, ids["report_id"], runs[1]["id"]),
                         {"BRA/tc.rvt": PASSING})

        report_page = self.http.get(f"/reports/{ids['report_id']}")
        self.assertEqual(report_page.status_code, 200)
        self.assertIn(b"pending", report_page.data)

    def test_queue_and_reports_pages(self):
        self.queue(PASSING)
        self.assertEqual(self.http.get("/runner/").status_code, 200)
        self.assertEqual(self.http.get("/reports/").status_code, 200)


if __name__ == "__main__":
    unittest.main()
