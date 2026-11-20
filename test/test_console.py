"""The editor's console over HTTP: opening it borrows the local worker,
and the page runs cards and forms and reads the transcript"""

import shutil
import tempfile
import time
import unittest
from pathlib import Path

from automationv3.services.database import connect, init_db
from automationv3.services.workspace import find_worktrees
from automationv3.services.worker import Host, Worker
from automationv3.services.worker.local import LocalServer
from automationv3.web.app import create_app

from . import gitutil
from .examples import RVTS

SCRIPT = "DSKY/tc_dsky_001.rst"


class ConsoleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        gitdir = self.tmp / "repo"
        shutil.copytree(RVTS, gitdir / "rvts")
        gitutil.create_repo(gitdir)
        self.branch = next(iter(find_worktrees(gitdir / "rvts")))
        self.db = self.tmp / "test.db"
        with connect(self.db) as conn:
            init_db(conn)
        (self.tmp / "reports").mkdir()
        host = Host.from_config({"environments": {"sim": {"workdir": str(self.tmp / "sim")}}})
        self.worker = Worker(LocalServer(self.db, self.tmp / "reports", "local://test"), host)
        self.worker.check_in(started=True)
        self.app = create_app(DB_PATH=self.db, REPORTS_PATH=self.tmp / "reports",
                              WORKSPACE_PATH=gitdir / "rvts", TESTING=True,
                              CONSOLE_WORKER=self.worker)
        self.http = self.app.test_client()
        self.base = f"/workspace/{self.branch}/console"

    def tearDown(self):
        found = self.app.config.get("_CONSOLE")
        if found is not None:
            found.close()
        shutil.rmtree(self.tmp)

    def post(self, route, **data):
        return self.http.post(self.base + route, json=data)

    def opened(self, **choices):
        response = self.post("/open", path=SCRIPT, **choices)
        self.assertEqual(response.status_code, 200, response.get_json())
        return self.idle()

    def idle(self, timeout=60):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            state = self.http.get(self.base + "/lines?since=0").get_json()["state"]
            if state and not state["busy"]:
                return state
            time.sleep(0.02)
        self.fail("the console didn't finish")

    def lines(self, since=0):
        return self.http.get(f"{self.base}/lines?since={since}").get_json()["lines"]

    def test_choices_for_a_script(self):
        answer = self.http.get(f"{self.base}?path={SCRIPT}").get_json()
        self.assertIsNone(answer["state"])
        self.assertEqual(answer["choices"]["environments"], ["sim"])
        self.assertEqual(answer["choices"]["defaults"]["versions"], {"lm": "LUM210"})
        self.assertIn("LUM099", answer["choices"]["versions"]["lm"])

    def test_open_borrows_the_worker_and_close_gives_it_back(self):
        state = self.opened(versions={"lm": "LUM131"})
        self.assertEqual(state["versions"], {"lm": "LUM131"})
        self.assertEqual(state["script"], SCRIPT)
        self.assertTrue(self.worker.borrowed)
        self.assertEqual(self.post("/close").status_code, 200)
        self.assertFalse(self.worker.borrowed)
        self.assertIsNone(self.http.get(self.base).get_json()["state"])

    def test_run_a_card_and_read_the_transcript(self):
        self.opened()
        last = self.lines()[-1]["n"]
        response = self.post("/run", kind="card", code="(Verify (+ 1 1) = 2)",
                             title="Arithmetic")
        self.assertEqual(response.status_code, 200)
        self.idle()
        texts = [line["text"] for line in self.lines(last)]
        self.assertEqual(texts[:2], ["▶ Arithmetic", "✓ (Verify (+ 1 1) = 2)"])

    def test_the_form_at_the_cursor(self):
        self.opened()
        last = self.lines()[-1]["n"]
        answer = self.post("/run", kind="form", code="(+ 1 1)\n(* 2\n   21)", line=2,
                           character=3).get_json()
        self.assertEqual(answer["ran"], {"text": "(* 2\n   21)", "line": 1, "character": 0})
        self.idle()
        self.assertEqual([l["text"] for l in self.lines(last)][-1], "=> 42")

    def test_forms_typed(self):
        self.opened()
        self.post("/run", kind="forms", text="(def x 5) (* x x)")
        self.idle()
        self.assertEqual(self.lines()[-1]["text"], "=> 25")

    def test_names(self):
        self.assertEqual(self.http.get(self.base + "/names").get_json(), {"names": []})
        self.opened()
        names = {n["name"] for n in self.http.get(self.base + "/names").get_json()["names"]}
        self.assertTrue({"lm", "dsky", "boot"} <= names)

    def test_controls(self):
        self.opened()
        self.post("/run", kind="forms", text="(def x 5)")
        self.idle()
        self.assertEqual(self.post("/reset").status_code, 200)
        self.idle()
        self.post("/run", kind="forms", text="x")
        self.idle()
        self.assertEqual(self.lines()[-1]["kind"], "fail", "reset forgot x")
        self.assertEqual(self.post("/clear").status_code, 200)
        self.assertEqual(self.lines(), [])
        self.assertEqual(self.post("/restart").status_code, 200)
        self.assertEqual(self.idle()["start"], "fresh")

    def test_nothing_runs_before_it_is_open(self):
        self.assertEqual(self.post("/run", kind="forms", text="1").status_code, 409)

    def test_a_script_not_saved_yet(self):
        response = self.post("/open", path="DSKY/new.rst")
        self.assertEqual(response.status_code, 400)

    def test_the_workspace_page_offers_it(self):
        page = self.http.get(f"/workspace/{self.branch}").get_data(as_text=True)
        self.assertIn('data-console="true"', page)
        self.assertIn("data-ed-console", page)
        app = create_app(DB_PATH=self.db, REPORTS_PATH=self.tmp / "reports",
                         WORKSPACE_PATH=self.tmp / "repo", TESTING=True)
        page = app.test_client().get(f"/workspace/{self.branch}").get_data(as_text=True)
        self.assertIn('data-console="false"', page)
        self.assertNotIn("data-ed-console", page)

    def test_outcomes_in_the_state(self):
        self.opened()
        command = self.post("/run", kind="forms", text="(Verify 1 = 2)").get_json()["command"]
        state = self.idle()
        self.assertEqual(state["outcomes"][str(command)], "fail")

    def test_no_console_without_a_worker_in_process(self):
        app = create_app(DB_PATH=self.db, REPORTS_PATH=self.tmp / "reports",
                         WORKSPACE_PATH=self.tmp / "repo", TESTING=True)
        self.assertEqual(app.test_client().get(self.base).status_code, 404)

    def test_attached_files_are_served(self):
        self.opened()
        self.post("/run", kind="card", code='(boot :standard :low-gate)\n'
                                             '(AttachTrajectory "flight")')
        self.idle()
        files = [l for l in self.lines() if l["kind"] == "file"]
        self.assertEqual(len(files), 2, self.lines())
        response = self.http.get(f"{self.base}/files/{files[1]['file']}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"<svg", response.data)
        response.close()


if __name__ == "__main__":
    unittest.main()
