"""Suspect links, workspace contexts, specs as pages, the requirements
pages and the requirement versions reports record"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from automationv3.framework.planning import build_plan
from automationv3.services import jobs
from automationv3.services.database import connect, init_db
from automationv3.services.reports import store as report_store
from automationv3.services.requirements import models, render, suspects, textdiff
from automationv3.web.app import create_app

from .test_jobs import PASSING, write_tree
from .test_requirement_store import ExportCase, SRS, SYS


def link(conn, workspace, script, id):
    with conn:
        conn.execute("INSERT INTO requirement_links VALUES (?, ?, ?)", (workspace, script, id))


class TestScriptSuspects(ExportCase):
    def setUp(self):
        super().setUp()
        self.load([("SYS", "1", {"index.rst": SYS}), ("SRS", "1", {"index.rst": SRS})],
                  sets=[("R1", {"SYS": "1", "SRS": "1"})])
        self.trunk()
        link(self.conn, "w", "a.rst", "SW-1")
        link(self.conn, "w", "b.rst", "SW-2")

    def suspects(self, context="trunk"):
        return [(s.source, s.target) for s in suspects.script_suspects(self.conn, "w", context)]

    def test_a_link_is_reviewed_against_the_text_it_first_meets(self):
        self.assertEqual(self.suspects(), [])

    def test_a_text_change_makes_its_scripts_suspect_until_reviewed(self):
        self.suspects()
        self.trunk(srs=SRS.replace("below 40%", "below 45%"))
        self.assertEqual(self.suspects(), [("a.rst", "SW-1")])
        suspects.review_script(self.conn, "w", "a.rst", "SW-1")
        self.assertEqual(self.suspects(), [])

    def test_other_changes_are_not_suspect(self):
        self.suspects()
        self.trunk(srs=SRS.replace(":verification: Test\n", "")
                          .replace("The software shall shed", "The *software* shall shed"))
        self.assertEqual(self.suspects(), [])

    def test_a_baseline_context_doesnt_move(self):
        self.suspects("set:R1")
        self.trunk(srs=SRS.replace("below 40%", "below 45%"))
        self.assertEqual(self.suspects("set:R1"), [])

    def test_the_reviewed_text_is_kept_to_compare(self):
        self.suspects()
        self.trunk(srs=SRS.replace("below 40%", "below 45%"))
        (s,) = suspects.script_suspects(self.conn, "w")
        self.assertIn("40%", suspects.reviewed_version(self.conn, "SW-1", s.reviewed).text)


class TestTraceSuspects(ExportCase):
    def test_a_parent_text_change_makes_its_children_suspect(self):
        self.trunk()
        self.assertEqual(suspects.trace_suspects(self.conn), [])
        self.trunk(sys=SYS.replace("shall work", "shall work well"))
        found = [(s.source, s.target) for s in suspects.trace_suspects(self.conn)]
        self.assertEqual(found, [("SW-1", "SYS-1"), ("SW-3", "SYS-1")])
        suspects.review_trace(self.conn, "SW-1", "SYS-1")
        self.assertEqual([s.source for s in suspects.trace_suspects(self.conn)], ["SW-3"])

    def test_a_new_link_starts_reviewed(self):
        self.trunk()
        self.trunk(sys=SYS.replace("shall work", "shall work well"),
                   srs=SRS.replace(".. requirement:: SW-2\n",
                                   ".. requirement:: SW-2\n   :satisfies: SYS-1\n"))
        self.assertNotIn("SW-2", [s.source for s in suspects.trace_suspects(self.conn)])


class TestWorkspaceContext(ExportCase):
    def test_the_context_comes_from_automation_json(self):
        self.load([("SRS", "1", {"index.rst": SRS})], sets=[("R1", {"SRS": "1"})])
        root = self.tmp / "ws"
        root.mkdir()
        self.assertEqual(models.workspace_context(self.conn, root), ("trunk", None))
        (root / "automation.json").write_text(json.dumps({"requirements": "set:R1"}))
        self.assertEqual(models.workspace_context(self.conn, root), ("set:R1", None))
        (root / "automation.json").write_text(json.dumps({"requirements": "set:R9"}))
        context, problem = models.workspace_context(self.conn, root)
        self.assertEqual(context, "trunk")
        self.assertIn("set:R9", problem)
        (root / "automation.json").write_text("{nope")
        self.assertEqual(models.workspace_context(self.conn, root)[0], "trunk")


class TestScriptPagesQuoteTheirContext(ExportCase):
    def test_rendering_is_cached_per_context(self):
        from automationv3.framework import rst
        from automationv3.framework.statements import get_statements
        self.load([("SRS", "1", {"index.rst": SRS})], sets=[("R1", {"SRS": "1"})])
        self.trunk(srs=SRS.replace("below 40%", "below 45%"))
        context = ["trunk"]
        rst.set_requirement_lookup(lambda id: models.find_by_id(self.conn, id, context[0]),
                                   lambda: context[0])
        self.addCleanup(rst.set_requirement_lookup, None)
        self.addCleanup(get_statements.cache_clear)
        script = "Title\n=====\n\nTests :req:`SW-1`.\n"
        self.assertIn("45%", get_statements(script)[0].html)
        context[0] = "set:R1"
        self.assertIn("40%", get_statements(script)[0].html)


class TestTextDiff(unittest.TestCase):
    def test_words_added_and_removed(self):
        self.assertEqual(textdiff.word_diff("shed below 40% now", "shed below 45% now"),
                         [("same", "shed below "), ("removed", "40%"), ("added", "45%"),
                          ("same", " now")])

    def test_punctuation_is_apart_from_words_but_numbers_keep_theirs(self):
        self.assertEqual(textdiff.word_diff("below 40%.", "below 4.5%."),
                         [("same", "below "), ("removed", "40%"), ("added", "4.5%"),
                          ("same", ".")])


INDEX = """Software
========

.. toctree::

   power

.. requirement:: SW-0

   The software shall start.
"""

POWER = """Power
=====

.. figure:: images/fig.png

   A figure.

.. requirement:: SW-1
   :satisfies: SYS-1
   :subsystem: EPS

   The software shall shed loads below 40%.
"""


@unittest.skipUnless(render.available(), "Sphinx isn't installed")
class TestRendering(ExportCase):
    def setUp(self):
        super().setUp()
        self.load([("SRS", None, {"index.rst": INDEX, "power.rst": POWER,
                                  "images/fig.png": "not really a png"})])
        self.version = models.resolve(self.conn)["SRS"]
        self.cache = self.tmp / "cache"

    def test_builds_pages_with_contents_and_where_each_requirement_is(self):
        out = render.build(self.conn, self.version, self.cache)
        nav = render.nav(out)
        self.assertEqual([c["doc"] for c in nav["children"]], ["power"])
        self.assertEqual(nav["requirements"], {"SW-0": "index", "SW-1": "power"})
        page = render.page(out, "power")
        self.assertEqual(page["title"], "Power")
        self.assertIn('href="@req/SYS-1"', page["body"])
        self.assertIn("subsystem", page["body"])
        self.assertTrue((out / "_images" / "fig.png").is_file())
        self.assertIsNone(render.page(out, "../etc"))
        self.assertIsNone(render.page(out, "nope"))

    def test_builds_once(self):
        out = render.build(self.conn, self.version, self.cache)
        marker = out / "nav.json"
        before = marker.stat().st_mtime_ns
        self.assertEqual(render.build(self.conn, self.version, self.cache), out)
        self.assertEqual(marker.stat().st_mtime_ns, before)


class TestPages(ExportCase):
    def setUp(self):
        super().setUp()
        self.conn.close()
        self.db = self.tmp / "db"
        self.conn = connect(self.db)
        init_db(self.conn)
        self.load([("SYS", "1", {"index.rst": SYS}), ("SRS", "1", {"index.rst": SRS})],
                  sets=[("R1", {"SYS": "1", "SRS": "1"})])
        self.trunk()
        self.trunk(sys=SYS.replace("shall work", "shall work well"),
                   srs=SRS.replace("below 40%", "below 45%"))
        app = create_app(DB_PATH=str(self.db), SPEC_CACHE_PATH=str(self.tmp / "cache"))
        app.testing = True
        self.http = app.test_client()

    def get(self, url, status=200):
        response = self.http.get(url)
        self.assertEqual(response.status_code, status, url)
        return response.get_data(True)

    def test_the_list_in_a_context(self):
        self.assertIn("45%", self.get("/requirements/?spec=SRS"))
        self.assertIn("40%", self.get("/requirements/?spec=SRS&context=set:R1"))
        self.get("/requirements/?context=set:R9", 404)

    def test_a_requirement_with_its_traces_and_history(self):
        page = self.get("/requirements/req/SW-1")
        self.assertIn("SYS-1", page)
        self.assertIn("changed since reviewed", page)  # SYS-1's text changed
        self.assertIn("<del>40%</del>", page)
        self.assertIn("SRS@1", page)
        self.get("/requirements/req/NOPE", 404)

    def test_changes_between_contexts(self):
        page = self.get("/requirements/changes?from=set:R1&to=trunk")
        self.assertIn("SW-1", page)
        self.assertIn("<ins>45%</ins>", page)
        self.assertNotIn("SW-2", page)

    def test_imports_and_suspects(self):
        self.assertIn("Import #", self.get("/requirements/imports"))
        self.assertIn("SW-3", self.get("/requirements/suspects"))

    def test_reviewing_a_trace(self):
        response = self.http.post("/requirements/review", data={
            "child": "SW-3", "parent": "SYS-1", "next": "/requirements/suspects"})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("SW-3", self.get("/requirements/suspects"))
        response = self.http.post("/requirements/review", data={
            "child": "SW-1", "parent": "SYS-1", "next": "https://elsewhere"})
        self.assertTrue(response.headers["Location"].endswith("/requirements/suspects"))

    @unittest.skipUnless(render.available(), "Sphinx isn't installed")
    def test_a_spec_as_a_page(self):
        page = self.get("/requirements/spec/set:R1/SRS/")
        self.assertIn("40%", page)
        self.assertIn('href="/requirements/req/SYS-1?context=set%3AR1"', page)
        response = self.http.get("/requirements/spec/trunk/SRS/?req=SW-3")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/spec/trunk/SRS/#SW-3"))
        self.get("/requirements/spec/trunk/NOPE/", 404)


class TestReportsRecordVersions(ExportCase):
    def setUp(self):
        super().setUp()
        self.reports = self.tmp / "reports"
        self.reports.mkdir()
        self.rvts = self.tmp / "rvts"
        write_tree(self.rvts, {"a.rst": PASSING})
        self.load([("SRS", "1", {"index.rst": SRS})], sets=[("R1", {"SRS": "1"})])
        self.trunk()

    def queue(self, context):
        plan = build_plan("", self.rvts, [], requirements=["SW-1"],
                          links={"SW-1": ["a.rst"]})
        return jobs.queue_plan(self.conn, self.reports, plan, context=context)

    def test_a_report_records_its_context_and_versions(self):
        report_id, (run_id, *_) = self.queue("set:R1")
        report = report_store.load_report(self.reports, report_id)
        self.assertEqual(report["requirement_context"], "set:R1")
        recorded = report["requirement_snapshots"]["SW-1"]
        self.assertIn("40%", recorded["text"])
        self.assertEqual((recorded["spec"], recorded["context"]), ("SRS", "set:R1"))
        run = report_store.load_run(self.reports, report_id, run_id)
        self.assertEqual(run["requirement_versions"], {"SW-1": recorded["text_hash"]})

    def test_a_trunk_report_links_to_trunk_as_it_was_tracked(self):
        report_id, _ = self.queue("trunk")
        (latest,) = self.conn.execute("SELECT MAX(id) FROM imports").fetchone()
        report = report_store.load_report(self.reports, report_id)
        self.assertEqual(report["requirement_snapshots"]["SW-1"]["context"], f"trunk@{latest}")

    def test_the_report_page_says_when_the_text_has_changed_since(self):
        from automationv3.web import reports as report_pages
        report_id, _ = self.queue("trunk")
        self.trunk(srs=SRS.replace("below 40%", "below 45%"))
        report = report_store.load_report(self.reports, report_id)
        app = create_app(DB_PATH=":memory:")
        with app.app_context():
            from flask import g
            g.db = self.conn
            self.assertEqual(report_pages.text_changed(report), {"SW-1"})


if __name__ == "__main__":
    unittest.main()
