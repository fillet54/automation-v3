import shutil
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask

import automationv3
from automationv3.database import close_db, connect, init_db
from automationv3.editor import workspace
from automationv3.framework.closure import resolve
from automationv3.framework.executor import execute_closure, execute_script
from automationv3.framework.uut import Version, uut_types
from automationv3.jobqueue import models, worker
from automationv3.jobqueue.views import jobqueue
from automationv3.plugins.sample import Demo, Sim
from automationv3.reports import store
from automationv3.reports.views import reports

from .data import make_workspaces as gitutil

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

ROOT_CORE = '''
"Shared"
(environments :sim)
(uut :demo)
(def limit 10)
(defn under-limit? [x] (< x limit))
'''


class Recorder:
    def __init__(self):
        self.events = []

    def __getattr__(self, name):
        return lambda **kw: self.events.append((name[3:], kw))


def write_tree(root, files):
    for path, text in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)


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


class TestClosure(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        write_tree(self.root, {
            "core.rvt": ROOT_CORE,
            "BRA/core.rvt": "(def limit 20)",
            "BRA/SUB/tc.rvt": "(under-limit? 15)",
            "FUE/core.rvt": "(defn fuel-ok? [] true)",
            "FUE/tc.rvt": "(import FUE)",
            "ENG/tc.rvt": '(import FUE) (import "BRA") (environments :bench)',
        })

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_ancestor_chain_skips_missing_cores(self):
        closure = resolve(self.root, "BRA/SUB/tc.rvt")
        self.assertEqual(closure.load_order,
                         ["core.rvt", "BRA/core.rvt", "BRA/SUB/tc.rvt"])
        self.assertEqual(closure.errors, [])

    def test_imports_follow_chain_once(self):
        closure = resolve(self.root, "ENG/tc.rvt")
        self.assertEqual(closure.load_order,
                         ["core.rvt", "FUE/core.rvt", "BRA/core.rvt", "ENG/tc.rvt"])
        # Importing a folder already in the chain adds nothing
        self.assertEqual(resolve(self.root, "FUE/tc.rvt").load_order,
                         ["core.rvt", "FUE/core.rvt", "FUE/tc.rvt"])

    def test_imports_add_to_the_implicit_chain(self):
        write_tree(self.root, {
            "FUE/core.rvt": "(def fuel 1)",
            "FUE/SUB/core.rvt": "(defn all-loaded? [] (= 12 (+ (+ limit fuel) 1)))",
            "FUE/SUB/tc.rvt": "(import BRA) (all-loaded?)",
        })
        closure = resolve(self.root, "FUE/SUB/tc.rvt")
        self.assertEqual(closure.load_order, ["core.rvt", "FUE/core.rvt",
                                              "FUE/SUB/core.rvt", "BRA/core.rvt",
                                              "FUE/SUB/tc.rvt"])
        self.assertEqual(closure.imports, ["BRA/core.rvt"])

        # Definitions from the chain and the import are all visible, and
        # the chain's own limit (10) wins over the imported BRA's (20)
        self.assertEqual(execute_closure(closure.files, closure.load_order, Recorder(),
                                         closure.imports),
                         "pass")

    def test_imports_see_chain_values_but_never_override_them(self):
        write_tree(self.root, {
            "LIB/core.rvt": "(def limit 99) (def lib-limit (+ limit 1))",
            "APP/core.rvt": "(defn check? [] (= 11 lib-limit))",
            "APP/tc.rvt": "(import LIB) (check?) (under-limit? 9)",
        })
        closure = resolve(self.root, "APP/tc.rvt")
        recorder = Recorder()
        outcome = execute_closure(closure.files, closure.load_order, recorder,
                                  closure.imports)
        self.assertEqual(outcome, "pass", recorder.events)

    def test_declarations_inherit_and_script_overrides(self):
        self.assertEqual(resolve(self.root, "BRA/SUB/tc.rvt").environments, ["sim"])
        closure = resolve(self.root, "ENG/tc.rvt")
        self.assertEqual(closure.environments, ["bench"])
        self.assertEqual(closure.uuts, ["demo"])

    def test_text_overrides_disk_and_changes_hash(self):
        on_disk = resolve(self.root, "BRA/SUB/tc.rvt")
        draft = resolve(self.root, "BRA/SUB/tc.rvt", text="(under-limit? 1)")
        self.assertEqual(draft.files["BRA/SUB/tc.rvt"], "(under-limit? 1)")
        self.assertNotEqual(on_disk.hash, draft.hash)
        self.assertEqual(on_disk.hash, resolve(self.root, "BRA/SUB/tc.rvt").hash)

    def test_lint(self):
        write_tree(self.root, {
            "BAD/core.rvt": "(Wait 1)",
            "BAD/tc.rvt": "(def x 1) (do (import FUE)) (import NOPE) (import ../..)",
        })
        errors = resolve(self.root, "BAD/tc.rvt").errors
        self.assertTrue(any("core.rvt may only contain" in e for e in errors))
        self.assertTrue(any("def x belongs in a core.rvt" in e for e in errors))
        self.assertTrue(any("only allowed at the top level" in e for e in errors))
        self.assertTrue(any("cannot import NOPE" in e for e in errors))
        self.assertTrue(any("outside the root" in e for e in errors))

    def test_core_is_not_a_script(self):
        self.assertTrue(resolve(self.root, "BRA/core.rvt").errors)


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

    def test_defn_steps_use_innermost_definitions(self):
        files = {
            "core.rvt": ROOT_CORE,
            "BRA/core.rvt": "(def limit 20)",
            "BRA/tc.rvt": "(uut :demo) (under-limit? 15) (Wait 1) (under-limit? 25)",
        }
        recorder = Recorder()
        outcome = execute_closure(files, ["core.rvt", "BRA/core.rvt", "BRA/tc.rvt"],
                                  recorder)
        self.assertEqual(outcome, "fail")
        ends = [kw for kind, kw in recorder.events if kind == "step_end"]
        # The directive is skipped; 15 < 20 passes, 25 fails
        self.assertEqual([(e["index"], e["passed"]) for e in ends],
                         [(1, True), (2, True), (3, False)])
        self.assertEqual(ends[0]["stdout"], "returned true")

    def test_definitions_do_not_leak_between_runs(self):
        execute_closure({"core.rvt": "(def leaked 1)", "a.rvt": ""},
                        ["core.rvt", "a.rvt"], Recorder())
        recorder = Recorder()
        execute_closure({"b.rvt": "(leaked)"}, ["b.rvt"], recorder)
        ends = [kw for kind, kw in recorder.events if kind == "step_end"]
        self.assertFalse(ends[0]["passed"])


class TestSamplePlugins(unittest.TestCase):
    def setUp(self):
        self.workdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.workdir)

    def test_registered(self):
        self.assertIs(uut_types()["demo"], Demo)

    def test_install(self):
        env, demo = Sim(workdir=self.workdir), Demo()
        self.assertIsNone(demo.installed_version(env))
        version = demo.list_versions()[0]
        demo.install(version, env)
        self.assertEqual(demo.installed_version(env), version)
        with self.assertRaises(ValueError):
            demo.install(Version("9.9.9", "x"), env)


class QueueTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "reports"
        self.root.mkdir()
        self.rvts = self.tmp / "rvts"
        write_tree(self.rvts, {"a.rvt": PASSING, "b.rvt": PASSING})
        self.db_file = self.tmp / "test.db"
        self.conn = connect(self.db_file)
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp)

    def queue(self, script="a.rvt", **kw):
        return models.queue_script(self.conn, self.root, self.rvts, script, **kw)


class TestJobModels(QueueTestCase):
    def test_claim_is_exclusive(self):
        _, run_id = self.queue()
        self.assertTrue(models.claim(self.conn, run_id, "http://w1"))
        self.assertFalse(models.claim(self.conn, run_id, "http://w2"))
        self.assertEqual(models.find_jobs(self.conn, "pending"), [])

    def test_release_returns_job_to_queue(self):
        _, run_id = self.queue()
        models.claim(self.conn, run_id, "http://w1")
        self.assertFalse(models.release(self.conn, run_id, "http://w2"))
        self.assertTrue(models.release(self.conn, run_id, "http://w1"))
        self.assertEqual([j.id for j in models.find_jobs(self.conn, "pending")], [run_id])

    def test_finish_writes_outcome_then_removes_job(self):
        report_id, run_id = self.queue()
        models.claim(self.conn, run_id, "http://w1")
        models.finish(self.conn, self.root, models.get_job(self.conn, run_id), "pass")
        self.assertIsNone(models.get_job(self.conn, run_id))
        run = store.load_run(self.root, report_id, run_id)
        self.assertEqual(run["outcome"], "pass")
        self.assertEqual(run["worker"], "http://w1")

    def test_run_records_closure(self):
        write_tree(self.rvts, {"core.rvt": "(def x 1)"})
        report_id, run_id = self.queue()
        run = store.load_run(self.root, report_id, run_id)
        self.assertEqual(run["load_order"], ["core.rvt", "a.rvt"])
        self.assertEqual(run["closure_hash"], resolve(self.rvts, "a.rvt").hash)
        self.assertEqual(store.read_closure(self.root, report_id, run_id),
                         {"core.rvt": "(def x 1)", "a.rvt": PASSING})

    def test_lint_errors_refuse_queueing(self):
        write_tree(self.rvts, {"bad.rvt": "(def x 1)"})
        with self.assertRaises(models.QueueError):
            self.queue("bad.rvt")
        self.assertEqual(models.find_jobs(self.conn), [])

    def test_choose_environment_and_versions(self):
        write_tree(self.rvts, {"core.rvt": ROOT_CORE})
        report_id, run_id = self.queue()
        job = models.get_job(self.conn, run_id)
        self.assertEqual(job.environment, "sim")
        self.assertEqual(job.uut_versions["demo"]["id"], "1.1.0")  # newest

        _, run_id = self.queue(versions={"demo": "1.0.0"})
        self.assertEqual(models.get_job(self.conn, run_id).uut_versions["demo"]["id"],
                         "1.0.0")
        for bad in ({"environment": "bench"}, {"versions": {"demo": "0.1"}}):
            with self.assertRaises(models.QueueError):
                self.queue(**bad)

    def test_jobs_for_worker_match_environment_and_uuts(self):
        write_tree(self.rvts, {"core.rvt": ROOT_CORE, "plain/core.rvt": ""})
        write_tree(self.rvts, {"plain/x.rvt": "(environments) (uut) (Wait 1)"})
        _, sim_job = self.queue()
        _, plain_job = self.queue("plain/x.rvt")

        models.save_worker(self.conn, "http://bare", "available", [], {})
        models.save_worker(self.conn, "http://sim", "available", ["demo"],
                           {"sim": {"os": "x"}})
        self.assertEqual([j.id for j in models.jobs_for_worker(self.conn, "http://bare")],
                         [plain_job])
        self.assertEqual([j.id for j in models.jobs_for_worker(self.conn, "http://sim")],
                         [sim_job, plain_job])
        self.assertEqual(models.get_worker(self.conn, "http://sim").environments,
                         {"sim": {"os": "x"}})

    def test_jobs_of_missing_workers_become_errors(self):
        models.save_worker(self.conn, "http://alive", "busy")
        models.save_worker(self.conn, "http://gone", "busy")
        _, alive_job = self.queue()
        report_id, gone_job = self.queue("b.rvt")
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
        report_id, run_id = self.queue()
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


class TestWorkerAgainstServer(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "reports"
        self.root.mkdir()

        # A git workspace whose rvts hold a sim/demo tree and a plain one
        gitdir = self.tmp / "repo"
        write_tree(gitdir / "rvts", {
            "core.rvt": ROOT_CORE,
            "BRA/tc.rvt": "(under-limit? 5) (Wait 1)",
            "plain/core.rvt": "(environments) (uut)",
            "plain/fail.rvt": FAILING,
            "plain/pass.rvt": PASSING,
            "plain/lint.rvt": "(def x 1)",
            "LIB/core.rvt": "(def limit 99)",
            "BRA/imports.rvt": "(import LIB) (under-limit? 50)",
        })
        gitutil.create_repo(gitdir)
        self.branch = next(iter(workspace.find_worktrees(gitdir)))

        app = Flask(__name__, template_folder=Path(automationv3.__file__).parent / "templates")
        app.register_blueprint(workspace.bp, url_prefix="/workspace")
        app.register_blueprint(jobqueue, url_prefix="/runner")
        app.register_blueprint(reports, url_prefix="/reports")
        app.teardown_appcontext(close_db)
        app.config["DB_PATH"] = self.tmp / "test.db"
        app.config["REPORTS_PATH"] = self.root
        app.config["WORKSPACE_PATH"] = gitdir
        app.testing = True
        with connect(app.config["DB_PATH"]) as conn:
            init_db(conn)
        self.http = app.test_client()

        self.simdir = self.tmp / "sim"
        session = FlaskSession(self.http, "http://server")
        self.worker = worker.ServerClient(
            "http://server", "http://w1",
            host=worker.Host.from_config({"environments": {"sim": {"workdir": str(self.simdir)}}}),
            session=session,
        )
        self.worker.keepalive("available", started=True)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def queue(self, script, **kw):
        response = self.http.post("/runner/jobs", json={
            "workspace": self.branch, "script": script, **kw})
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def test_worker_runs_queued_script(self):
        ids = self.queue("plain/fail.rvt")
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

    def test_installs_uut_once_and_records_it(self):
        ids = self.queue("BRA/tc.rvt", uut_versions={"demo": "1.0.0"})
        self.assertEqual(worker.work_once(self.worker), "pass")
        run = store.load_run(self.root, ids["report_id"], ids["run_id"])
        self.assertEqual(run["environment"], "sim")
        self.assertEqual(run["installed"]["demo"]["id"], "1.0.0")
        self.assertEqual(run["installed"]["demo"]["action"], "installed")
        self.assertEqual(run["fingerprint"]["environment"], "sim")

        # Same version again is kept, a different one is installed
        self.http.post(f"/reports/{ids['report_id']}/runs/{ids['run_id']}/rerun")
        worker.work_once(self.worker)
        latest = store.list_runs(self.root, ids["report_id"])[-1]
        self.assertEqual(latest["installed"]["demo"]["action"], "kept")
        self.assertEqual(latest["uut_versions"], run["uut_versions"])

        self.queue("BRA/tc.rvt", uut_versions={"demo": "1.1.0"})
        worker.work_once(self.worker)
        self.assertEqual(Demo().installed_version(Sim(workdir=self.simdir)).id, "1.1.0")

    def test_worker_keeps_chain_definitions_over_imports(self):
        ids = self.queue("BRA/imports.rvt")
        # LIB's limit (99) would let 50 pass; the chain's 10 must win
        self.assertEqual(worker.work_once(self.worker), "fail")
        run = store.load_run(self.root, ids["report_id"], ids["run_id"])
        self.assertEqual(run["imports"], ["LIB/core.rvt"])

    def test_worker_without_environment_skips_sim_jobs(self):
        bare = worker.ServerClient("http://server", "http://bare",
                                   session=self.worker.session)
        bare.keepalive("available", started=True)
        self.queue("BRA/tc.rvt")
        self.assertIsNone(worker.work_once(bare))
        self.assertEqual(worker.work_once(self.worker), "pass")

    def test_queue_rejects_lint_errors(self):
        response = self.http.post("/runner/jobs", json={
            "workspace": self.branch, "script": "plain/lint.rvt"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("belongs in a core.rvt", response.get_json()["errors"][0])

    def test_only_holder_can_report(self):
        ids = self.queue("plain/pass.rvt")
        self.assertIsNotNone(self.worker.claim(ids["run_id"]))
        response = self.http.post(f"/runner/jobs/{ids['run_id']}/complete",
                                  json={"worker_url": "http://w2", "outcome": "pass"})
        self.assertEqual(response.status_code, 409)

    def test_restarted_worker_errors_its_jobs(self):
        ids = self.queue("plain/pass.rvt")
        self.worker.claim(ids["run_id"])
        self.worker.keepalive("available", started=True)
        run = store.load_run(self.root, ids["report_id"], ids["run_id"])
        self.assertEqual(run["outcome"], "error")

    def test_rerun_adds_run_to_same_report(self):
        ids = self.queue("plain/pass.rvt")
        worker.work_once(self.worker)
        response = self.http.post(f"/reports/{ids['report_id']}/runs/{ids['run_id']}/rerun")
        self.assertEqual(response.status_code, 302)

        runs = store.list_runs(self.root, ids["report_id"])
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[1]["closure_hash"], runs[0]["closure_hash"])
        self.assertEqual(store.read_closure(self.root, ids["report_id"], runs[1]["id"]),
                         {"plain/core.rvt": "(environments) (uut)",
                          "core.rvt": ROOT_CORE,
                          "plain/pass.rvt": PASSING})

        report_page = self.http.get(f"/reports/{ids['report_id']}")
        self.assertEqual(report_page.status_code, 200)
        self.assertIn(b"pending", report_page.data)

    def test_queue_and_reports_pages(self):
        self.queue("plain/pass.rvt")
        self.assertEqual(self.http.get("/runner/").status_code, 200)
        self.assertEqual(self.http.get("/reports/").status_code, 200)

    def test_viewer_shows_script_and_run_panel(self):
        page = self.http.get(f"/workspace/{self.branch}/view?path=BRA/tc.rvt")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"under-limit?", page.data)
        self.assertIn(b'name="environment"', page.data)
        self.assertIn(b'name="version-demo"', page.data)

        page = self.http.get(f"/workspace/{self.branch}/view?path=plain/lint.rvt")
        self.assertIn(b"belongs in a core.rvt", page.data)
        self.assertNotIn(b'hx-post', page.data)

    def test_viewer_run_queues_and_redirects(self):
        response = self.http.post(f"/workspace/{self.branch}/run?path=BRA/tc.rvt",
                                  data={"environment": "sim", "version-demo": "1.0.0"})
        self.assertEqual(response.status_code, 204)
        self.assertTrue(response.headers["HX-Redirect"].startswith("/reports/"))
        (job,) = models.find_jobs(connect(self.tmp / "test.db"))
        self.assertEqual(job.uut_versions["demo"]["id"], "1.0.0")


if __name__ == "__main__":
    unittest.main()
