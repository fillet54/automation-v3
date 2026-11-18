"""The workspace editor's routes: a file as cards, saved to disk"""

import json
from contextlib import closing
import re
import shutil
import tempfile
import unittest
from html import unescape
from pathlib import Path

from automationv3.services.database import connect, init_db
from automationv3.web.app import create_app
from automationv3.web import editor
from .central import Central
from . import gitutil

SCRIPT = """\
Brakes
======
Checks the brakes.

.. rvt::
   :definitions:

   (def target 60)

Steps
-----

.. rvt:: Check it

   (Verify target = 60)
"""


def page_cards(html):
    """The cards on a page, as the browser script reads them"""
    return [json.loads(unescape(found))
            for found in re.findall(r'data-card="([^"]*)"', html)]


class TestEditor(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.repo = self.tmp / "master"
        self.rvts = self.repo / "rvts"
        (self.rvts / "BRA").mkdir(parents=True)
        (self.rvts / "core.rst").write_text("Core\n====\n\n.. rvt::\n\n   (environments :sim)\n")
        self.script = self.rvts / "BRA" / "brakes.rst"
        self.script.write_text(SCRIPT)
        (self.rvts / "notes.txt").write_text("one\ntwo\n")
        gitutil.create_repo(self.repo)
        with closing(connect(self.tmp / "a.db")) as conn:
            init_db(conn)
        self.app = create_app(DB_PATH=str(self.tmp / "a.db"), WORKSPACE_PATH=self.repo,
                              REPORTS_PATH=str(self.tmp / "reports"))
        self.app.testing = True
        self.client = self.app.test_client()

    def view(self, path="BRA/brakes.rst", **params):
        response = self.client.get("/workspace/master/view", query_string={"path": path, **params})
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def save(self, cards, path="BRA/brakes.rst", **body):
        return self.client.post("/workspace/master/editor/save", query_string={"path": path},
                                json={"cards": cards, **body})

    def test_a_script_shows_as_its_cards(self):
        html = self.view()
        found = page_cards(html)
        self.assertEqual([c["kind"] for c in found], ["prose", "rvt", "prose", "rvt"])
        self.assertEqual("".join(c["source"] for c in found), SCRIPT)
        self.assertEqual(found[3]["title"], "Check it")
        self.assertIn(f'data-hash="{editor.text_hash(SCRIPT)}"', html)
        self.assertIn('data-editable="true"', html)
        self.assertIn('<h1 class="ed-heading">Brakes</h1>', html)
        self.assertIn("Checks the brakes.", html)

    def test_a_variation_or_the_checked_in_view_is_not_cards(self):
        self.script.write_text(SCRIPT + "\nMore.\n")
        self.assertNotIn("data-ed-doc", self.view(files="checked in"))
        self.assertIn("data-ed-doc", self.view())

    def test_saving_untouched_cards_writes_the_same_file(self):
        found = page_cards(self.view())
        response = self.save(found, hash=editor.text_hash(SCRIPT), count=len(found))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.script.read_text(), SCRIPT)
        self.assertEqual(response.json["hash"], editor.text_hash(SCRIPT))

    def test_saving_an_edited_card(self):
        found = page_cards(self.view())
        found[1] = {"kind": "rvt", "source": None, "index": None, "code": "(def target 70)",
                    "definitions": True, "variations": []}
        found.insert(3, {"kind": "prose", "source": None, "text": "A new paragraph."})
        response = self.save(found, hash=editor.text_hash(SCRIPT), count=4)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.script.read_text(), SCRIPT.replace("target 60)\n\nSteps", "target 70)\n\nSteps")
                         .replace("-----\n\n.. rvt:: Check", "-----\n\nA new paragraph.\n\n.. rvt:: Check"))

    def test_a_save_is_refused_when_the_file_changed(self):
        found = page_cards(self.view())
        opened = editor.text_hash(SCRIPT)
        self.script.write_text(SCRIPT + "\nSomeone else was here.\n")
        response = self.save(found, hash=opened, count=4)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json["hash"], editor.disk_hash(self.script))
        self.assertIn("Someone else", self.script.read_text())
        diff = self.client.post("/workspace/master/editor/diff", query_string={"path": "BRA/brakes.rst"},
                                json={"cards": found, "count": 4}).json["lines"]
        self.assertIn("-Someone else was here.", diff)
        self.assertEqual(self.save(found, hash=opened, count=4, force=True).status_code, 200)
        self.assertEqual(self.script.read_text(), SCRIPT)

    def test_the_state_of_a_file(self):
        state = self.client.get("/workspace/master/editor/state", query_string={"path": "BRA/brakes.rst"})
        self.assertEqual(state.json["hash"], editor.text_hash(SCRIPT))
        gone = self.client.get("/workspace/master/editor/state", query_string={"path": "BRA/none.rst"})
        self.assertIsNone(gone.json["hash"])

    def test_rendering_an_edited_card(self):
        def render(card, **more):
            return self.client.post("/workspace/master/editor/render", json={"card": card, **more}).json["html"]
        self.assertIn("<h2", render({"kind": "prose", "text": "New title\n---------\nWith *words*."}))
        self.assertIn("<em>words</em>", render({"kind": "prose", "text": "With *words*."}))
        self.assertIn("Verify", render({"kind": "rvt", "code": "(Verify 1 = 1)", "title": "Check"}))
        self.assertIn("ed-unreadable", render({"kind": "rvt", "code": "(Verify 1 = 1"}))
        self.assertIn("<pre", render({"kind": "source", "text": "a < b"}, plain=True))

    def test_a_variant_holds_its_cards(self):
        text = SCRIPT + "\n.. rvt-variant::\n   :variations: fast\n\n   Only fast.\n\n   .. rvt::\n\n      (Verify 1 = 1)\n"
        self.script.write_text(text)
        html = self.view()
        self.assertIn('<section class="ed-card ed-card--variant"', html)
        self.assertIn('<div class="ed-variant__body">', html)
        self.assertIn("Only for</span> <code>fast</code>", html)
        found = page_cards(html)  # the variant, then what it holds
        self.assertEqual([c["kind"] for c in found], ["prose", "rvt", "prose", "rvt", "variant", "prose", "rvt"])
        variant, prose, block = found[4:]
        self.assertEqual(variant["count"], 2)
        # untouched, as it was
        sent = found[:4] + [{**variant, "children": [prose, block]}]
        self.assertEqual(self.save(sent, hash=editor.text_hash(text), count=5).status_code, 200)
        self.assertEqual(self.script.read_text(), text)
        # a child changed: the variant is written again
        block = {**block, "source": None, "code": "(Verify 2 = 2)"}
        sent = found[:4] + [{**variant, "source": None, "variations": ["fast", "slow"], "children": [prose, block]}]
        self.assertEqual(self.save(sent, hash=editor.text_hash(text), count=5).status_code, 200)
        self.assertEqual(self.script.read_text(), text.replace("fast\n", "fast, slow\n").replace("1 = 1", "2 = 2"))

    def test_variants_dont_nest_without_end(self):
        card = {"kind": "variant", "source": None, "variations": ["x"], "children": []}
        for _ in range(20):
            card = {"kind": "variant", "source": None, "variations": ["x"], "children": [card]}
        self.assertEqual(self.save([card], force=True).status_code, 400)

    def test_a_plain_text_file_is_one_card(self):
        (card,) = page_cards(self.view("notes.txt"))
        self.assertEqual((card["kind"], card["text"]), ("source", "one\ntwo"))
        card = {"kind": "source", "source": None, "text": "one\ntwo\nthree"}
        self.assertEqual(self.save([card], "notes.txt", hash=editor.text_hash("one\ntwo\n"), count=1).status_code, 200)
        self.assertEqual((self.rvts / "notes.txt").read_text(), "one\ntwo\nthree\n")

    def test_paths_stay_in_the_workspace(self):
        self.assertEqual(self.save([], "../../outside.rst", force=True).status_code, 404)
        self.assertEqual(self.save([], "BRA", force=True).status_code, 404)
        self.assertEqual(self.save([{"kind": "nonsense"}], force=True).status_code, 400)

    def post(self, what, **body):
        return self.client.post(f"/workspace/master/editor/{what}", json=body)

    def test_a_new_script_opens_unsaved(self):
        response = self.post("new", folder="BRA", title="Brake  Wear")
        self.assertEqual(response.status_code, 200, response.get_data(True))
        found = response.json
        self.assertEqual(found["path"], "BRA/brake_wear.rst")
        self.assertFalse((self.rvts / "BRA" / "brake_wear.rst").exists())
        text = "".join(c["data"]["source"] for c in found["cards"])
        self.assertEqual(text, "==========\nBrake Wear\n==========\n\nRequirements\n------------\n\n"
                               "Steps\n-----\n\n.. rvt::\n\n   (TBD)\n")
        self.assertIn("Brake Wear", found["cards"][0]["html"])
        # its tab shows an empty document until it is saved
        html = self.view("BRA/brake_wear.rst")
        self.assertIn('data-hash=""', html)
        self.assertIn("isn't on disk yet", html)
        saved = self.save([c["data"] for c in found["cards"]], "BRA/brake_wear.rst",
                          hash="", count=found["count"])
        self.assertEqual(saved.status_code, 200)
        self.assertEqual((self.rvts / "BRA" / "brake_wear.rst").read_text(), text)
        self.assertIn("brake_wear.rst", self.client.get("/workspace/master/tree").get_data(True))

    def test_a_new_script_needs_a_free_name_and_a_title(self):
        self.assertEqual(self.post("new", folder="BRA", title=" ").status_code, 400)
        self.assertEqual(self.post("new", folder="BRA", title="x", name="brakes.rst").status_code, 409)
        self.assertEqual(self.post("new", folder="BRA", title="x", name="../up.rst").status_code, 400)
        self.assertEqual(self.post("new", folder="nope", title="x").status_code, 400)
        self.assertEqual(self.post("new", folder="../..", title="x").status_code, 404)
        self.assertEqual(self.post("new", folder="", title="x", name="given").json["path"], "given.rst")

    def test_a_new_script_for_a_requirement(self):
        found = self.post("new", folder="", title="Wear", requirement="LGC-GDN-001").json
        text = "".join(c["data"]["source"] for c in found["cards"])
        self.assertIn("Requirements\n------------\n1. :req:`LGC-GDN-001`\n", text)

    def test_a_clone_opens_unsaved_under_its_new_title(self):
        found = self.post("clone", **{"from": "BRA/brakes.rst"}, folder="", title="Brakes again").json
        self.assertEqual(found["path"], "brakes_again.rst")
        text = "".join(c["data"]["source"] for c in found["cards"])
        self.assertEqual(text, SCRIPT.replace("Brakes\n======", "Brakes again\n============"))
        self.assertFalse((self.rvts / "brakes_again.rst").exists())
        self.assertEqual(self.post("clone", **{"from": "notes.txt"}, folder="", title="x").status_code, 400)

    def test_retitling(self):
        self.assertEqual(editor.retitled("===\nOld\n===\nBody.\n", "A longer one"),
                         "============\nA longer one\n============\nBody.\n")
        self.assertEqual(editor.retitled("Just words.\n", "Title"), "=====\nTitle\n=====\n\nJust words.\n")

    def test_renaming_and_moving(self):
        response = self.post("move", **{"from": "BRA/brakes.rst"}, folder="", name="stop.rst")
        self.assertEqual(response.json, {"path": "stop.rst"})
        self.assertEqual((self.rvts / "stop.rst").read_text(), SCRIPT)
        self.assertFalse(self.script.exists())
        self.assertEqual(self.post("move", **{"from": "stop.rst"}, folder="", name="core.rst").status_code, 409)
        self.assertEqual(self.post("move", **{"from": "stop.rst"}, folder="", name="a/b.rst").status_code, 400)
        self.assertEqual(self.post("move", **{"from": "gone.rst"}, folder="", name="b.rst").status_code, 404)

    def test_deleting(self):
        self.assertEqual(self.post("delete", path="BRA/brakes.rst").status_code, 200)
        self.assertFalse(self.script.exists())
        self.assertEqual(self.post("delete", path="BRA").status_code, 404)
        self.assertEqual(self.post("delete", path="../../x").status_code, 404)

    def test_a_new_folder(self):
        self.assertEqual(self.post("folder", folder="BRA", name="wear", core=True).json, {"path": "BRA/wear"})
        self.assertEqual((self.rvts / "BRA" / "wear" / "core.rst").read_text(),
                         "wear definitions\n================\n\n.. rvt::\n   :definitions:\n")
        self.assertEqual(self.post("folder", folder="", name="BRA").status_code, 409)
        self.assertIn("BRA/wear", self.client.get("/workspace/master/editor/folders").json["folders"])
        self.assertIn("core.rst", self.client.get("/workspace/master/tree").get_data(True))

    def test_tabs_are_remembered(self):
        put = self.client.put("/workspace/master/tabs",
                              json={"paths": ["BRA/brakes.rst", "core.rst", "gone.rst"], "active": "core.rst"})
        self.assertEqual(put.status_code, 200)
        page = self.client.get("/workspace/master").get_data(as_text=True)
        self.assertIn('data-tabs=\'["BRA/brakes.rst", "core.rst"]\'', page)
        self.assertIn('data-active="core.rst"', page)
        linked = self.client.get("/workspace/master?path=notes.txt").get_data(as_text=True)
        self.assertIn('data-active="notes.txt"', linked)
        self.assertIn('"notes.txt"]', linked)


class TestCentralServerDoesNotEdit(unittest.TestCase):
    def test_no_editing(self):
        server = Central(scripts={"BRA/tc.rst": SCRIPT})
        self.addCleanup(server.close)
        ann = server.client("ann@example.com")
        branch = next(iter(server.app.config["WORKSPACES"].branches()))
        html = ann.get(f"/workspace/{branch}/view", query_string={"path": "BRA/tc.rst"}).get_data(as_text=True)
        self.assertIn('data-editable="false"', html)
        saved = ann.post(f"/workspace/{branch}/editor/save", query_string={"path": "BRA/tc.rst"},
                         json={"cards": [], "force": True})
        self.assertEqual(saved.status_code, 403)


if __name__ == "__main__":
    unittest.main()
