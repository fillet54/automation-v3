import json
import os
import shutil
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from automationv3.plugins.apollo import LunarModule
from automationv3.services import builds, client
from automationv3.services import scratch as scratch_service
from automationv3.services.database import connect, init_db
from automationv3.services.workspace import find_worktrees
from automationv3.web.app import create_app

from .central import SCRIPTS, Central, HttpSession
from . import gitutil
from .rvt import doc, rvt

LM_SCRIPTS = {
    **SCRIPTS,
    "lm/core.rst": rvt("(environments :sim) (uut :lm)"),
    "lm/tc.rst": doc("Uses the lunar module", rvt("(Wait 1)")),
}


class BuildsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.build_repo = self.tmp / "build-repo"
        self.build_out = self.tmp / "lm-build"
        self.build_out.mkdir()
        env = mock.patch.dict(os.environ, {"AUTOMATION_LM_BUILDS": str(self.build_repo),
                                           "AUTOMATION_CONFIG_HOME": str(self.tmp / "config")})
        env.start()
        self.addCleanup(env.stop)
        (self.tmp / "config").mkdir()
        (self.tmp / "config" / "client.json").write_text(
            json.dumps({"builds": {"lm": str(self.build_out)}}))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def make_build(self, label="build-1"):
        """A rope built on this machine: LUM210's flags, its own revision"""
        rope = {"revision": f"LUM210-{label}", "flags": {"extended_missions": True}}
        (self.build_out / "luminary.json").write_text(json.dumps(rope))
        return builds.find_local_build("lm")


class TestLunarModuleBuilds(BuildsTest):
    def test_find_and_upload(self):
        self.assertIsNone(builds.find_local_build("lm"))
        build = self.make_build()
        self.assertTrue(build.id.startswith("local-"))
        self.assertNotIn(build.digest, [v.digest for v in LunarModule().list_versions()])
        version = LunarModule().upload_build(build)
        self.assertEqual((version.id, version.digest), (build.id, build.digest))
        self.assertIn(version, LunarModule().list_versions())

    def test_choices(self):
        server = {"lm": [{"id": "LUM099", "digest": "a"}, {"id": "LUM210", "digest": "b"}]}
        (choice,) = builds.choices(["lm"], server)
        self.assertEqual((choice.selected, choice.needs_upload), ("LUM210", False))

        build = self.make_build()
        (choice,) = builds.choices(["lm"], server)
        self.assertTrue(choice.needs_upload)
        self.assertEqual(choice.options[0][0], builds.UPLOAD)
        self.assertEqual(choice.selected, "LUM210")  # not uploaded: keep the newest

        builds.remember_used({"lm": "LUM099"})
        (choice,) = builds.choices(["lm"], server)
        self.assertEqual(choice.selected, "LUM099")
        self.assertIn(("LUM099", "LUM099 (last used)"), choice.options)

        server["lm"].append({"id": build.id, "digest": build.digest})
        (choice,) = builds.choices(["lm"], server)
        self.assertEqual((choice.selected, choice.needs_upload), (build.id, False))
        self.assertIn((build.id, f"{build.id} (your local build)"), choice.options)


class TestBuildsInTheClient(BuildsTest):
    def setUp(self):
        super().setUp()
        self.central = Central(scripts=LM_SCRIPTS)
        self.addCleanup(self.central.close)
        token = self.central.token("user", "laptop", "ann@example.com")
        self.remote = client.CentralClient(
            "http://server", token, session=HttpSession(self.central.app.test_client()))
        repo = self.tmp / "clone"
        for path, text in LM_SCRIPTS.items():
            (repo / "rvts" / path).parent.mkdir(parents=True, exist_ok=True)
            (repo / "rvts" / path).write_text(text)
        gitutil.create_repo(repo)
        self.branch = next(iter(find_worktrees(repo / "rvts")))
        with closing(connect(self.tmp / "client.db")) as conn:
            init_db(conn)
        (self.tmp / "reports").mkdir()
        self.http = create_app(DB_PATH=self.tmp / "client.db", WORKSPACE_PATH=repo / "rvts",
                               REPORTS_PATH=self.tmp / "reports", CENTRAL=self.remote,
                               TESTING=True).test_client()

    def view(self):
        return self.http.get(f"/workspace/{self.branch}/view?path=lm/tc.rst").get_data(True)

    def test_a_new_local_build_is_offered_uploaded_and_used(self):
        self.assertNotIn("New local build", self.view())
        build = self.make_build()
        page = self.view()
        self.assertIn("New local build", page)
        self.assertIn(f"upload your local build ({build.id})", page)

        response = self.http.post("/scratch/run", data={
            "workspace": self.branch, "script": "lm/tc.rst", "version-lm": "upload"})
        self.assertEqual(response.status_code, 302, response.get_data(True))
        self.assertTrue((self.build_repo / build.id / "luminary.json").is_file())
        (run,) = scratch_service.scratch_runs(self.central.reports)
        self.assertEqual(run["uut_versions"]["lm"]["id"], build.id)
        self.assertEqual(builds.last_used("lm"), build.id)

        page = self.view()
        self.assertNotIn("New local build", page)
        self.assertIn(f"{build.id} (your local build, last used)", page)

    def test_the_cli_uses_and_lists_local_builds(self):
        from automationv3 import cli
        import io
        from contextlib import redirect_stdout
        client.remember("http://server", self.remote.token, "ann@example.com")
        build = self.make_build("build-2")
        with mock.patch.object(client.requests, "Session",
                               lambda: HttpSession(self.central.app.test_client())):
            out = io.StringIO()
            with redirect_stdout(out):
                code = cli.list_builds(client.CentralClient.signed_in())
            self.assertEqual(code, 0)
            self.assertIn(f"lm: {build.id}", out.getvalue())
            self.assertIn("not uploaded yet", out.getvalue())
            with redirect_stdout(io.StringIO()):
                versions = cli.local_versions(client.CentralClient.signed_in(),
                                              {"lm": "local"})
            self.assertEqual(versions, {"lm": build.id})
            out = io.StringIO()
            with redirect_stdout(out):
                cli.list_builds(client.CentralClient.signed_in())
            self.assertIn(f"uploaded as {build.id}", out.getvalue())


class TestUploadedBuildsAreForScratch(BuildsTest):
    def test_reports_dont_offer_or_take_uploaded_builds(self):
        from automationv3.framework.planning import build_plan
        build = self.make_build()
        LunarModule().upload_build(build)
        server = Central(scripts=LM_SCRIPTS)
        self.addCleanup(server.close)
        root = server.gitdir / "rvts"
        report = build_plan("", root, ["lm/tc.rst"], versions={"lm": build.id})
        self.assertNotIn(build.id, report.uut_choices["lm"])
        self.assertIn(f"UUT lm has no version {build.id}", report.errors)
        scratch = build_plan("", root, ["lm/tc.rst"], versions={"lm": build.id},
                             scratch=True)
        self.assertEqual(scratch.errors, [])
        self.assertEqual(scratch.uut_versions["lm"]["id"], build.id)
