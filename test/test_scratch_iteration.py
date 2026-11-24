"""Trying a script over and over: which variations a scratch run runs, the
way back from a run to the line that failed, and the console prompt's
language help"""

import json
import re
import shutil
import tempfile
import unittest
from contextlib import closing
from html import unescape
from pathlib import Path

from automationv3.services import scratch as scratch_service
from automationv3.services.database import connect, init_db
from automationv3.services.worker import Host, Worker
from automationv3.services.worker.local import LocalServer
from automationv3.web import editor
from automationv3.web.app import create_app
from . import gitutil

CORE = """\
Core
====

.. rvt::

   (defn double [x] (* 2 x))
"""

SCRIPT = """\
Speeds
======

.. rvt::

   (variations "speed" ["slow" [1] "mid" [5] "fast" [9]])

Steps
-----

.. rvt:: Fast enough

   (Verify speed > 0)
   (Verify speed > 4)
"""

FAILING_LINE = SCRIPT.splitlines().index("   (Verify speed > 4)") + 1


class TestScratchIteration(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        rvts = self.tmp / "master" / "rvts"
        (rvts / "SPD").mkdir(parents=True)
        (rvts / "core.rst").write_text(CORE)
        (rvts / "SPD" / "speeds.rst").write_text(SCRIPT)
        gitutil.create_repo(self.tmp / "master")
        self.db = self.tmp / "a.db"
        with closing(connect(self.db)) as conn:
            init_db(conn)
        self.reports = self.tmp / "reports"
        self.app = create_app(DB_PATH=str(self.db), WORKSPACE_PATH=rvts,
                              REPORTS_PATH=str(self.reports))
        self.app.testing = True
        self.client = self.app.test_client()

    def run_in_scratch(self, **form):
        response = self.client.post("/scratch/run", data={
            "workspace": "master", "script": "SPD/speeds.rst", **form})
        self.assertEqual(response.status_code, 302, response.get_data(True))
        return response

    def variations_run(self):
        return sorted(r["variation"]["name"] for r in scratch_service.scratch_runs(self.reports))

    def page(self, address, **params):
        response = self.client.get(address, query_string=params)
        self.assertEqual(response.status_code, 200, address)
        return response.get_data(as_text=True)

    # Which variations

    def test_the_run_dialog_offers_each_variation(self):
        html = self.page("/workspace/master/view", path="SPD/speeds.rst")
        self.assertIn("data-ed-run-vars", html)
        for name in ("slow", "mid", "fast"):
            self.assertIn(f'name="variation" value="{name}" checked', html)
        self.assertIn('name="filter"', html)
        # one picked beside the file's name: only it is ticked
        html = self.page("/workspace/master/view", path="SPD/speeds.rst", variation="mid")
        self.assertIn('name="variation" value="mid" checked', html)
        self.assertIn('name="variation" value="slow">', html)

    def test_only_the_ticked_variations_run(self):
        self.run_in_scratch(variation=["slow", "fast"])
        self.assertEqual(self.variations_run(), ["fast", "slow"])

    def test_the_filter_narrows_the_ticked_ones(self):
        self.run_in_scratch(variation=["slow", "mid", "fast"], filter="(> speed 4)")
        self.assertEqual(self.variations_run(), ["fast", "mid"])

    def test_none_given_runs_every_variation(self):
        self.run_in_scratch()
        self.assertEqual(self.variations_run(), ["fast", "mid", "slow"])

    def test_a_filter_that_leaves_nothing_says_so(self):
        response = self.client.post("/scratch/run", data={
            "workspace": "master", "script": "SPD/speeds.rst", "filter": "(> speed 100)"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Nothing to run", response.get_data(as_text=True))

    # Back to the editor

    def failed_run(self):
        self.run_in_scratch(variation=["slow"])
        worker = Worker(LocalServer(str(self.db), self.reports, "local://w"), Host())
        worker.check_in(started=True)
        self.assertEqual(worker.work_once(), "fail")
        (run,) = scratch_service.scratch_runs(self.reports)
        return run

    def test_a_failed_run_goes_back_to_the_line_that_failed(self):
        run = self.failed_run()
        html = self.page(f"/reports/scratch/runs/{run['id']}")
        self.assertIn("Edit at the failure", html)
        edit = unescape(re.search(r'href="([^"]*)"[^>]*data-run-edit', html).group(1))
        self.assertIn("path=SPD/speeds.rst", edit.replace("%2F", "/"))
        self.assertIn(f"line={FAILING_LINE}", edit)
        self.assertIn(f"run={run['id']}", edit)
        # the failure's excerpt links there too
        self.assertIn(f"line={FAILING_LINE}", html[html.index('class="failure'):])

        # the editor: the run to go back to, or to run again
        html = self.page("/workspace/master", path="SPD/speeds.rst", line=FAILING_LINE,
                         col=3, run=run["id"])
        self.assertIn("data-ed-from-run", html)
        self.assertIn(f"/reports/scratch/runs/{run['id']}", html)
        self.assertIn(f"/scratch/runs/{run['id']}/again", html)
        self.assertIn(f'data-line="{FAILING_LINE}"', html)

        # the file's view says which card, and where in its code
        html = self.page("/workspace/master/view", path="SPD/speeds.rst", line=FAILING_LINE, col=3)
        goto = json.loads(unescape(re.search(r'data-goto="([^"]*)"', html).group(1)))
        self.assertEqual(goto, {"card": 3, "line": 1, "character": 0})

    def test_a_run_from_elsewhere_isnt_offered_in_the_editor(self):
        html = self.page("/workspace/master", path="SPD/speeds.rst", run="../../etc")
        self.assertNotIn("data-ed-from-run", html)
        html = self.page("/workspace/master", path="SPD/speeds.rst", run="nope")
        self.assertNotIn("data-ed-from-run", html)

    def test_the_scratch_list_links_to_the_editor(self):
        self.failed_run()
        html = self.page("/scratch/")
        self.assertIn(f"line={FAILING_LINE}", html)

    def test_locate_finds_the_innermost_card(self):
        path = Path("x.rst")
        self.assertEqual(editor.locate(path, SCRIPT, 1), {"card": 0, "line": 0, "character": 0})
        self.assertEqual(editor.locate(path, SCRIPT, FAILING_LINE - 1, 5),
                         {"card": 3, "line": 0, "character": 2})
        self.assertIsNone(editor.locate(path, SCRIPT, 999))

    # The console prompt

    def ask(self, method, code, line=0, character=None):
        response = self.client.post("/workspace/master/lsp", json={
            "session": "page", "start": True,
            "request": {"method": method, "path": "SPD/speeds.rst", "code": code, "line": line,
                        "character": len(code.split("\n")[line]) if character is None else character}})
        self.assertEqual(response.status_code, 200, response.get_data(True))
        return response.json["result"]

    def test_the_prompt_completes_what_the_script_knows(self):
        labels = [i["label"] for i in self.ask("completion", "(Verify (dou")["items"]]
        self.assertIn("double", labels)   # from core.rst
        self.assertIn("speed", labels)    # a variation's value
        self.assertIn("Verify", [i["label"] for i in self.ask("completion", "(Ver")["items"]])
        # a second line of the prompt
        labels = [i["label"] for i in self.ask("completion", "(do\n  (Verify sp", line=1)["items"]]
        self.assertIn("speed", labels)

    def test_the_prompt_has_hover_and_signatures(self):
        hover = self.ask("hover", "(double speed)", character=3)
        self.assertIn("double", hover["contents"]["value"])
        self.assertEqual(hover["range"]["start"], {"line": 0, "character": 1})
        found = self.ask("signature", "(double ")
        self.assertTrue(found["signatures"])

    def test_asking_about_the_prompt_leaves_the_script_as_it_was(self):
        self.ask("completion", "(Verify sp")
        from automationv3.web.editor import lsp_session
        with self.app.test_request_context():
            from automationv3.web.workspace import workspace_or_404
            service = lsp_session(workspace_or_404("master"), "page").server.service
        self.assertNotIn("SPD/speeds.rst", service.texts)


if __name__ == "__main__":
    unittest.main()
