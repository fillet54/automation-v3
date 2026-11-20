"""Snippets: titled blocks of the snippets.rst files from the root down
to a file's folder, offered to the editor and the console"""

import shutil
import tempfile
import unittest
from pathlib import Path

from automationv3.framework import closure, snippets
from automationv3.lsp.service import Service
from automationv3.services.database import connect, init_db
from automationv3.services.workspace import find_worktrees
from automationv3.web.app import create_app

from . import gitutil
from .examples import RVTS

TOP = """\
Snippets
========

Checks a value.

.. rvt:: Check

   (Verify #{name} = #{value})#{}

.. rvt:: Wait

   (Wait 2s)
"""

DEEPER = """\
Here
====

The folder's own check.

.. rvt:: Check

   (Verify here = 1)
"""


class ReadTest(unittest.TestCase):
    def test_titled_blocks_are_snippets(self):
        found, problems = snippets.read(TOP)
        self.assertEqual(problems, [])
        self.assertEqual([s.name for s in found], ["Check", "Wait"])
        check = found[0]
        self.assertEqual(check.description, "Checks a value.")
        self.assertEqual(check.code, "(Verify #{name} = #{value})#{}")
        self.assertEqual(check.line, 6)
        self.assertEqual(found[1].description, "")  # nothing right before it

    def test_plain_text_names_the_fields(self):
        self.assertEqual(snippets.plain("(Verify #{name} = #{ value })#{}"), "(Verify name = value)")

    def test_a_block_without_a_title_or_a_name_taken_twice_is_a_problem(self):
        text = TOP + "\n.. rvt::\n\n   (Wait 1s)\n\n.. rvt:: Wait\n\n   (Wait 3s)\n"
        found, problems = snippets.read(text)
        self.assertEqual([s.name for s in found], ["Check", "Wait"])
        self.assertEqual(len(problems), 2)
        self.assertIn("needs a name", problems[0].message)
        self.assertIn("already called Wait", problems[1].message)

    def test_a_snippets_file_is_not_a_script(self):
        self.assertFalse(closure.is_script("A/snippets.rst", TOP))
        self.assertTrue(closure.is_script("A/tc.rst", TOP))


class CollectTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        (self.root / "A" / "B").mkdir(parents=True)
        (self.root / "snippets.rst").write_text(TOP)
        (self.root / "A" / "B" / "snippets.rst").write_text(DEEPER)

    def test_a_file_sees_its_folder_and_those_above(self):
        found = snippets.collect(self.root, "A/B/tc.rst")
        self.assertEqual([(s.name, s.path) for s in found],
                         [("Check", "A/B/snippets.rst"), ("Wait", "snippets.rst")])
        self.assertEqual([s.name for s in snippets.collect(self.root, "A/tc.rst")], ["Check", "Wait"])
        self.assertEqual(snippets.collect(self.root, "A/tc.rst")[0].path, "snippets.rst")

    def test_texts_being_edited_stand_in_for_the_disk(self):
        found = snippets.collect(self.root, "A/tc.rst", {"snippets.rst": DEEPER})
        self.assertEqual([s.code for s in found], ["(Verify here = 1)"])

    def test_the_language_server_reports_their_problems(self):
        service = Service(self.root)
        service.texts["snippets.rst"] = TOP + "\n.. rvt::\n\n   (Wait 1s)\n"
        (problem,) = service.problems()["snippets.rst"]
        self.assertIn("needs a name", problem.message)
        self.assertEqual(problem.line, 13)  # 0-based: the block on line 14

    def test_the_example_snippets_read_cleanly(self):
        for path in RVTS.rglob("snippets.rst"):
            found, problems = snippets.read(path.read_text(), str(path))
            self.assertEqual(problems, [], path)
            self.assertTrue(found, path)


class RouteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        gitdir = self.tmp / "repo"
        shutil.copytree(RVTS, gitdir / "rvts")
        gitutil.create_repo(gitdir)
        self.branch = next(iter(find_worktrees(gitdir / "rvts")))
        db = self.tmp / "test.db"
        with connect(db) as conn:
            init_db(conn)
        (self.tmp / "reports").mkdir()
        app = create_app(DB_PATH=db, REPORTS_PATH=self.tmp / "reports", WORKSPACE_PATH=gitdir / "rvts",
                         TESTING=True)
        self.http = app.test_client()

    def get(self, path):
        return self.http.get(f"/workspace/{self.branch}/snippets", query_string={"path": path})

    def test_a_script_gets_its_folders_snippets(self):
        found = self.get("LND/tc_lnd_001.rst").get_json()["snippets"]
        names = [s["name"] for s in found]
        self.assertEqual(names[0], "Land and check")  # LND's own come first
        self.assertIn("Precondition: LM booted", names)
        first = found[0]
        self.assertEqual(first["path"], "LND/snippets.rst")
        self.assertIn("#{descent}", first["code"])
        self.assertIn('"descent"', first["text"])

    def test_a_new_file_needs_no_file_on_disk(self):
        names = [s["name"] for s in self.get("DSKY/not_yet.rst").get_json()["snippets"]]
        self.assertNotIn("Land and check", names)
        self.assertIn("Wait for a value", names)

    def test_a_path_outside_the_workspace_is_refused(self):
        self.assertEqual(self.get("../x.rst").status_code, 400)


if __name__ == "__main__":
    unittest.main()
