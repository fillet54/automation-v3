"""A report as a formal document: its PDF, its bundle, and freezing"""

import hashlib
import json
import shutil
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from automationv3 import cli
from automationv3.framework.requirement import Requirement
from automationv3.services import jobs as models
from automationv3.documents import core, template
from automationv3.services.reports import build, export, store
from automationv3.services.reports.data import ReportData
from automationv3.services.requirements import models as requirement_models
from automationv3.services.worker import Host
from automationv3.services.worker.local import run_locally
from automationv3.services.workspace import find_worktrees
from automationv3.web.app import create_app

from .data import make_workspaces as gitutil
from .test_jobs import PASSING, QueueTestCase

RVTS = Path(__file__).resolve().parent / "data" / "rvts"
HAS_LATEX = shutil.which("latexmk") is not None


class ReportTestCase(unittest.TestCase):
    """One report: a script whose variations all pass, and one that fails"""

    @classmethod
    def setUpClass(cls):
        cls.source = Path(tempfile.mkdtemp())
        host = Host.from_config({"environments": {"sim": {"workdir": str(cls.source / "sim")}}})
        cls.report_id, _ = run_locally(
            RVTS, ["BRA/tc_bra_00004.rst", "BRA/tc_bra_00003.rst"], cls.source / "reports",
            host, versions={"demo": "1.0.0"})
        store.update_report(cls.source / "reports", cls.report_id,
                            requirements={"REQ-1": ["BRA/tc_bra_00004.rst"],
                                          "REQ-2": ["BRA/tc_bra_00003.rst"]},
                            requirement_snapshots={"REQ-1": {"text": "The brakes shall hold."}})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.source)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "reports"
        shutil.copytree(self.source / "reports", self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def report(self):
        return store.load_report(self.root, self.report_id)


def body(root, report_id, text=None, **extra):
    """The HTML of a report's document (its own report.rst, or `text`);
    ExportError if it has problems"""
    context = export.context(root, report_id, **extra)
    document = export.render_document(context, text or export.source(root, report_id))
    if export.problems(document):
        raise export.ExportError("; ".join(export.problems(document)))
    return core.write(document, "html5")["body"]


class TestDocument(ReportTestCase):
    def test_the_data_judges_each_combination_on_its_latest_run(self):
        data = ReportData(self.root, self.report_id)
        states = {(r["script"], r["variation"]): r["state"] for r in data.combinations}
        self.assertEqual(states[("BRA/tc_bra_00004.rst", "normal")], "pass")
        self.assertEqual(states[("BRA/tc_bra_00003.rst", None)], "fail")
        colors = {r["id"]: r["color"] for r in data.requirements}
        self.assertEqual(colors, {"REQ-1": "green", "REQ-2": "red"})

    def test_a_failure_names_its_step_and_why(self):
        data = ReportData(self.root, self.report_id)
        (failed,) = [r for r in data.combinations if r["state"] == "fail"]
        self.assertIn("step", failed["failure"]["step"])
        self.assertTrue(failed["failure"]["message"])

    def test_the_default_document_has_every_section_and_renders_cleanly(self):
        html = body(self.root, self.report_id)
        for heading in ("Identification", "Summary", "Open issues", "Requirements",
                        "Results", "Failures", "Bundle"):
            self.assertIn(f">{heading}</h", html)
        self.assertIn("The brakes shall hold.", html)
        self.assertIn("<em>text not recorded</em>", html)  # REQ-2 has no text

    def test_the_directives_stay_in_the_source(self):
        source = export.source(self.root, self.report_id)
        self.assertIn(".. results::", source)
        self.assertNotIn("list-table", source)

    def test_runs_are_named_by_their_whole_id(self):
        html = body(self.root, self.report_id)
        for run in store.list_runs(self.root, self.report_id):
            self.assertIn(run["id"], html)

    def test_an_empty_report_renders(self):
        report_id = models.create_report(self.root, "", "Empty")
        self.assertIn("None", body(self.root, report_id))

    def test_prose_and_report_values_mix(self):
        html = body(self.root, self.report_id,
                    "Covers :report:`requirements` requirements, "
                    ":report:`requirements.green` green, on demo :report:`uut.demo`.\n")
        self.assertIn("Covers 2 requirements, 1 green, on demo 1.0.0.", html)

    def test_directive_options_filter(self):
        html = body(self.root, self.report_id, ".. results::\n   :state: fail\n")
        self.assertIn("tc_bra_00003", html)
        self.assertNotIn("tc_bra_00004", html)

    def test_a_problem_in_the_source_stops_the_document(self):
        with self.assertRaisesRegex(export.ExportError, "no-such-directive"):  # unknown
            body(self.root, self.report_id, ".. no-such-directive::\n")

    def test_requirements_link_to_the_server_as_tested(self):
        export.store.update_report(self.root, self.report_id, requirement_snapshots={
            "REQ-1": {"text": "The brakes shall hold.", "spec": "SRS",
                      "context": "set:Release 1"}})
        html = body(self.root, self.report_id, ".. requirement-results::\n",
                    links=export.ServerLinks("http://server:8000/"))
        self.assertIn("http://server:8000/requirements/spec/set%3ARelease%201/SRS/?req=REQ-1",
                      html)

    def test_text_is_never_markup(self):
        rst = template.text("*bold* `x` |sub| 1. not a list")
        html = body(self.root, self.report_id, rst)
        self.assertEqual(html.count("<strong>"), 0)
        self.assertIn("*bold*", html)

    def test_text_that_could_open_a_block_stays_a_paragraph(self):
        for value in ["- x", "1. x", ":x: y", "..", "===", "see::", "tc_bra_ x"]:
            html = body(self.root, self.report_id, template.text(value)).strip()
            self.assertRegex(html, r"\A<p>[^<]*</p>\Z", value)  # one plain paragraph
        self.assertEqual(template.text("BRA/tc_bra_00004.rst"), "BRA/tc_bra_00004.rst")

    def test_verdicts_carry_a_class_each_output_can_style(self):
        self.assertIn('<span class="verdict-fail"><strong>fail</strong></span>',
                      body(self.root, self.report_id))

    def test_a_requirement_is_its_own_rst_when_it_stands_alone(self):
        self.assertIn(".. container:: requirement",
                      template.requirement("The brakes *shall* hold:\n\n- on ice"))
        # a section, or a role plain docutils doesn't know, falls back to text
        for value in ["Title\n=====\n\nText.", "See :ref:`x`."]:
            self.assertNotIn("container", template.requirement(value), value)

    def test_a_report_starts_from_its_workspace_template(self):
        mine = self.tmp / "mine"
        shutil.copytree(export.BUILTIN_TEMPLATE, mine)
        (mine / "report.rst").write_text("Ours\n====\n\n.. report-summary::\n")
        (mine / "snippets" / "report").mkdir(parents=True)
        (mine / "snippets" / "report" / "summary.rst").write_text(
            "We ran {{ data.runs | length }} runs.\n")
        report_id = models.create_report(self.root, "", "Mine", template=mine)
        self.assertIn("Ours", export.source(self.root, report_id))
        self.assertIn("We ran 0 runs.", body(self.root, report_id))
        (mine / "report.rst").write_text("Changed later\n")  # the report kept its copy
        self.assertIn("Ours", export.source(self.root, report_id))

    def test_document_fields_default_from_the_report(self):
        self.assertEqual(export.document_fields(self.report())["title"],
                         self.report()["name"])
        self.assertEqual(export.missing_fields(self.report()),
                         ["number", "revision", "author"])
        export.set_document(self.root, self.report_id, number="N-1", revision="A",
                            author="Me")
        self.assertEqual(export.missing_fields(self.report()), [])

    def test_the_title_is_the_reports_name(self):
        export.set_document(self.root, self.report_id, title="  Brake   tests ")
        self.assertEqual(self.report()["name"], "Brake tests")
        self.assertEqual(export.document_fields(self.report())["title"], "Brake tests")
        with self.assertRaises(export.ExportError):
            export.rename(self.root, self.report_id, " ")
        store.set_frozen(self.root, self.report_id, True)
        with self.assertRaises(export.ExportError):
            export.rename(self.root, self.report_id, "Other")

    def test_documents_are_lines_of_number_revision_title(self):
        documents = export.parse_documents("SRS-1 | C | Requirements | v2\n\nICD | B", "applicable")
        self.assertEqual(documents, [
            {"kind": "applicable", "number": "SRS-1", "revision": "C",
             "title": "Requirements | v2"},
            {"kind": "applicable", "number": "ICD", "revision": "B", "title": ""},
        ])
        self.assertEqual(export.format_documents(documents, "applicable"),
                         "SRS-1 | C | Requirements | v2\nICD | B | ")

    def test_a_workspace_template_is_its_rvts_sibling_report_folder(self):
        workspace = self.tmp / "repo" / "rvts"
        workspace.mkdir(parents=True)
        self.assertEqual(export.find_template(workspace), export.BUILTIN_TEMPLATE)
        shutil.copytree(export.BUILTIN_TEMPLATE, self.tmp / "repo" / "report")
        self.assertEqual(export.find_template(workspace), self.tmp / "repo" / "report")


@unittest.skipUnless(HAS_LATEX, "needs latexmk")
class TestExport(ReportTestCase):
    def test_the_site_is_the_document_and_a_page_per_run(self):
        export.export(self.root, self.report_id, out_dir=self.tmp / "out")
        site = build.site(self.root, self.report_id)
        index = (site / "index.html").read_text()
        self.assertIn("<!--ui:top-->", index)  # the app fills its shell when it serves it
        runs = store.list_runs(self.root, self.report_id)
        for run in runs:
            self.assertTrue((site / "runs" / f"{run['id']}.html").is_file())
            self.assertIn(f'href="runs/{run["id"]}.html"', index)  # results link their runs
        page = (site / "runs" / f"{runs[-1]['id']}.html").read_text()
        self.assertIn("Outcome", page)  # the run's summary, then its script with results
        self.assertIn('class="result fail', page)
        self.assertNotIn("automation-run:", index)  # every marker rewritten
        status = build.status(self.root, self.report_id)
        self.assertEqual(status["state"], "done")
        self.assertIn("automationv3.plugins.sample", status["plugins"])  # what built it
        self.assertIn(".attached-files", (site / "_static" / "plugins.css").read_text())
        self.assertIn(status["manifest_hash"],
                      (build.build_dir(self.root, self.report_id) / "report.tex").read_text())

    def test_the_bundle_holds_the_report_and_a_manifest_the_pdf_names(self):
        export.set_document(self.root, self.report_id, title="Brakes", number="TR-1",
                            revision="A", author="Me",
                            signatures={"Approved by": "J. Doe"},
                            documents=[{"kind": "applicable", "number": "SRS-1",
                                        "revision": "C", "title": "Requirements"}])
        path = export.export(self.root, self.report_id, out_dir=self.tmp / "out")
        name = f"report-{self.report_id}"
        self.assertEqual(path, self.tmp / "out" / f"{name}.zip")
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            for member in ("report.pdf", "report.tex", "MANIFEST.sha256",
                           f"{name}/report.json", f"{name}/report.rst",
                           f"{name}/template/template.json"):
                self.assertIn(f"{name}/{member}", names)
            manifest = zf.read(f"{name}/MANIFEST.sha256")
            for line in manifest.decode().splitlines():
                digest, member = line.split("  ")
                self.assertEqual(hashlib.sha256(zf.read(f"{name}/{member}")).hexdigest(),
                                 digest, member)
            tex = zf.read(f"{name}/report.tex").decode()
            bundled = json.loads(zf.read(f"{name}/{name}/report.json"))
        self.assertIn(hashlib.sha256(manifest).hexdigest(), tex)
        self.assertIn("J. Doe", tex)
        self.assertIn("SRS-1", tex)
        self.assertTrue(bundled["frozen"])
        self.assertTrue(store.is_frozen(self.report()))

    def test_by_default_bundles_go_in_the_report_folder_and_are_never_bundled(self):
        first = export.export(self.root, self.report_id)
        self.assertEqual(export.exports(self.root, self.report_id), [first])
        export.reopen(self.root, self.report_id)
        second = export.export(self.root, self.report_id)
        with zipfile.ZipFile(second) as zf:
            self.assertFalse([n for n in zf.namelist() if "/exports/" in n])

    def test_snapshots_fill_in_what_the_report_lacks(self):
        export.export(self.root, self.report_id, out_dir=self.tmp / "out",
                      snapshots={"REQ-1": {"text": "Other"},
                                 "REQ-2": {"text": "The brakes shall stop."},
                                 "REQ-9": {"text": "Not in the report"}})
        self.assertEqual(self.report()["requirement_snapshots"], {
            "REQ-1": {"text": "The brakes shall hold."},
            "REQ-2": {"text": "The brakes shall stop."}})


class TestExportRefusals(ReportTestCase):
    def test_a_failed_export_leaves_the_report_as_it_was(self):
        with self.assertRaises(export.ExportError):
            export.export(self.root, self.report_id, template=self.tmp / "no-template",
                          snapshots={"REQ-2": {"text": "x"}})
        self.assertFalse(store.is_frozen(self.report()))
        self.assertNotIn("REQ-2", self.report()["requirement_snapshots"])

    def test_bad_latex_is_reported_and_the_build_can_be_redone(self):
        if not HAS_LATEX:
            self.skipTest("needs latexmk")
        template = self.tmp / "template"
        shutil.copytree(export.BUILTIN_TEMPLATE, template)
        (template / "latex.tex_t").write_text(r"\documentclass{article}\begin{document}\oops")
        with self.assertRaises(export.ExportError) as e:
            export.export(self.root, self.report_id, template=template)
        self.assertIn("LaTeX", str(e.exception))
        # it stays frozen, its build failed: fix and rebuild
        self.assertTrue(store.is_frozen(self.report()))
        self.assertEqual(build.status(self.root, self.report_id)["state"], "failed")

    def test_unfinished_runs_refuse_an_export(self):
        run = store.list_runs(self.root, self.report_id)[0]
        store.update_run(self.root, self.report_id, run["id"], outcome=None)
        with self.assertRaises(export.ExportError) as e:
            export.export(self.root, self.report_id)
        self.assertIn("haven't finished", str(e.exception))

    def test_a_frozen_report_keeps_its_document(self):
        store.set_frozen(self.root, self.report_id, True)
        with self.assertRaises(export.ExportError):
            export.set_document(self.root, self.report_id, title="Changed")
        export.reopen(self.root, self.report_id)
        export.set_document(self.root, self.report_id, title="Changed")
        self.assertEqual(self.report()["name"], "Changed")


class TestFrozenQueue(QueueTestCase):
    def test_a_frozen_report_takes_no_runs_until_reopened(self):
        report_id, run_id = self.queue()
        models.claim(self.conn, run_id, "http://w1")
        models.finish(self.conn, self.root, models.get_job(self.conn, run_id), "pass")
        store.set_frozen(self.root, report_id, True)

        with self.assertRaises(models.QueueError) as e:
            models.rerun(self.conn, self.root, report_id, run_id)
        self.assertIn("frozen", e.exception.errors[0])
        plan = models.build_plan("", self.rvts, ["b.rst"])
        with self.assertRaises(models.QueueError):
            models.add_plan(self.conn, self.root, report_id, plan)
        self.assertEqual(len(store.list_runs(self.root, report_id)), 1)
        self.assertEqual(models.reports_for(self.root, ""), [])

        export.reopen(self.root, report_id)
        models.rerun(self.conn, self.root, report_id, run_id)
        self.assertEqual(len(store.list_runs(self.root, report_id)), 2)

    def test_adding_requirements_keeps_their_text(self):
        requirement_models.insert(self.conn, [Requirement("R-1", "Shall pass.", "X")])
        report_id = models.create_report(self.root, "")
        plan = models.build_plan("", self.rvts, ["a.rst"])
        models.add_plan(self.conn, self.root, report_id, plan,
                        {"R-1": ["a.rst"], "R-2": ["a.rst"]})
        snapshots = store.load_report(self.root, report_id)["requirement_snapshots"]
        self.assertEqual({k: v["text"] for k, v in snapshots.items()}, {"R-1": "Shall pass."})


class TestCli(ReportTestCase):
    def cli(self, *args):
        out = StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit) as exit:
            cli.main(["report", *args])
        return exit.exception.code, out.getvalue()

    def test_edit_sets_the_document_fields(self):
        folder = str(self.root / self.report_id)
        code, out = self.cli("edit", folder, "--title", "Brakes", "--number", "TR-1",
                             "--sign", "Approved by=J. Doe",
                             "--applicable", "SRS-1 | C | Requirements",
                             "--reference", "PLAN-2 | A | Test plan")
        self.assertEqual(code, 0, out)
        document = self.report()["document"]
        self.assertEqual((self.report()["name"], document["number"]), ("Brakes", "TR-1"))
        self.assertEqual(document["signatures"], {"Approved by": "J. Doe"})
        self.assertEqual([d["kind"] for d in document["documents"]],
                         ["applicable", "reference"])

        self.cli("edit", folder, "--applicable", "SRS-2 | D | New requirements")
        documents = self.report()["document"]["documents"]
        self.assertEqual([d["number"] for d in documents], ["PLAN-2", "SRS-2"])

    def test_not_a_report_folder(self):
        code, out = self.cli("reopen", str(self.tmp))
        self.assertEqual(code, 2)
        self.assertIn("isn't a report folder", out)

    @unittest.skipUnless(HAS_LATEX, "needs latexmk")
    def test_export_freezes_and_reopen_unfreezes(self):
        folder = str(self.root / self.report_id)
        code, out = self.cli("export", folder, "--out", str(self.tmp / "out"))
        self.assertEqual(code, 0, out)
        self.assertIn("Warning: the report has no document number", out)
        self.assertTrue((self.tmp / "out" / f"report-{self.report_id}.zip").exists())
        self.assertEqual(self.cli("edit", folder, "--title", "X")[0], 1)
        self.assertEqual(self.cli("reopen", folder)[0], 0)
        self.assertFalse(store.is_frozen(self.report()))


class TestWeb(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        gitdir = self.tmp / "repo"
        (gitdir / "rvts").mkdir(parents=True)
        (gitdir / "rvts" / "a.rst").write_text(PASSING)
        gitutil.create_repo(gitdir)
        self.branch = next(iter(find_worktrees(gitdir)))
        self.root = self.tmp / "reports"
        self.root.mkdir()
        app = create_app(DB_PATH=self.tmp / "test.db", REPORTS_PATH=self.root,
                         WORKSPACE_PATH=gitdir, TESTING=True, BUILD_WAIT=True)
        from automationv3.services.database import connect, init_db
        with connect(self.tmp / "test.db") as conn:
            init_db(conn)
        self.http = app.test_client()
        self.report_id = models.create_report(self.root, self.branch, "Nightly")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_the_document_form_sets_the_fields(self):
        page = self.http.get(f"/reports/{self.report_id}/document")
        self.assertIn(b"Quality Assurance", page.data)  # the template's roles
        self.http.post(f"/reports/{self.report_id}/document", data={
            "number": "TR-1", "revision": "A", "author": "Me",
            "sign-2": "J. Doe", "applicable": "SRS-1 | C | Requirements", "reference": ""})
        response = self.http.post(f"/reports/{self.report_id}/rename", data={
            "name": "Brakes", "next": f"/reports/{self.report_id}/history"})
        self.assertEqual(response.headers["Location"], f"/reports/{self.report_id}/history")
        document = store.load_report(self.root, self.report_id)["document"]
        self.assertEqual(document["signatures"], {"Approved by": "J. Doe"})
        self.assertEqual(document["documents"][0]["number"], "SRS-1")
        page = self.http.get(f"/reports/{self.report_id}")
        self.assertIn(b"Brakes", page.data)
        self.assertIn(b">Freeze</button>", page.data)

    @unittest.skipUnless(HAS_LATEX, "needs latexmk")
    def test_freeze_export_download_and_reopen(self):
        base = f"/reports/{self.report_id}"
        response = self.http.post(f"{base}/export")
        self.assertEqual(response.status_code, 302)
        # frozen and built: the report is its site, in the app's shell
        self.assertEqual(self.http.get(base).headers["Location"], f"{base}/site/")
        site = self.http.get(f"{base}/site/").get_data(True)
        self.assertIn("Frozen", site)
        self.assertIn('class="ui-header"', site)
        self.assertIn(f'action="{base}/reopen"', site)
        self.assertNotIn("Add a test", site)
        self.assertEqual(self.http.get(f"{base}/site/_static/ui.css").status_code, 200)
        pdf = self.http.get(f"{base}/report.pdf")
        self.assertEqual((pdf.status_code, pdf.data[:4]), (200, b"%PDF"))
        pdf.close()
        bundle = self.http.post(f"{base}/bundle")
        self.assertEqual(bundle.status_code, 200)
        bundle.close()
        name = f"report-{self.report_id}.zip"
        download = self.http.get(f"{base}/exports/{name}")
        self.assertEqual(download.status_code, 200)
        download.close()
        self.assertEqual(self.http.get(f"{base}/document").status_code, 302)

        self.http.post(f"{base}/reopen")
        self.assertFalse(store.is_frozen(store.load_report(self.root, self.report_id)))
        self.assertIsNone(build.status(self.root, self.report_id))  # its build is gone

    def test_an_export_that_cant_run_says_why(self):
        run_id = store.create_run(self.root, self.report_id, "a.rst", {"a.rst": PASSING})
        response = self.http.post(f"/reports/{self.report_id}/export")
        self.assertEqual(response.status_code, 409)
        self.assertIn(b"haven&#39;t finished", response.data)
        self.assertIsNotNone(run_id)


if __name__ == "__main__":
    unittest.main()
