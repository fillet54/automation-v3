import json
import os
import shutil
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from automationv3.plugins.sample import Demo
from automationv3.services import builds, client
from automationv3.services import jobs as models
from automationv3.services.database import connect, init_db
from automationv3.services.workspace import find_worktrees
from automationv3.web.app import create_app

from .central import SCRIPTS, Central, HttpSession
from .data import make_workspaces as gitutil
from .rvt import doc, rvt

DEMO_SCRIPTS = {
    **SCRIPTS,
    "demo/core.rst": rvt("(environments :sim) (uut :demo)"),
    "demo/tc.rst": doc("Uses the demo", rvt("(Wait 1)")),
}


class BuildsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.build_repo = self.tmp / "build-repo"
        self.build_out = self.tmp / "demo-build"
        self.build_out.mkdir()
        env = mock.patch.dict(os.environ, {"AUTOMATION_DEMO_BUILDS": str(self.build_repo),
                                           "AUTOMATION_CONFIG_HOME": str(self.tmp / "config")})
        env.start()
        self.addCleanup(env.stop)
        (self.tmp / "config").mkdir()
        (self.tmp / "config" / "client.json").write_text(
            json.dumps({"builds": {"demo": str(self.build_out)}}))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def make_build(self, content=b"build 1"):
        (self.build_out / "demo.bin").write_bytes(content)
        return builds.find_local_build("demo")


class TestDemoBuilds(BuildsTest):
    def test_find_and_upload(self):
        self.assertIsNone(builds.find_local_build("demo"))
        build = self.make_build()
        self.assertTrue(build.id.startswith("local-"))
        self.assertNotIn(build.digest, [v.digest for v in Demo().list_versions()])
        version = Demo().upload_build(build)
        self.assertEqual((version.id, version.digest), (build.id, build.digest))
        self.assertIn(version, Demo().list_versions())

    def test_choices(self):
        server = {"demo": [{"id": "1.0.0", "digest": "a"}, {"id": "1.1.0", "digest": "b"}]}
        (choice,) = builds.choices(["demo"], server)
        self.assertEqual((choice.selected, choice.needs_upload), ("1.1.0", False))

        build = self.make_build()
        (choice,) = builds.choices(["demo"], server)
        self.assertTrue(choice.needs_upload)
        self.assertEqual(choice.options[0][0], builds.UPLOAD)
        self.assertEqual(choice.selected, "1.1.0")  # not uploaded: keep the newest

        builds.remember_used({"demo": "1.0.0"})
        (choice,) = builds.choices(["demo"], server)
        self.assertEqual(choice.selected, "1.0.0")
        self.assertIn(("1.0.0", "1.0.0 (last used)"), choice.options)

        server["demo"].append({"id": build.id, "digest": build.digest})
        (choice,) = builds.choices(["demo"], server)
        self.assertEqual((choice.selected, choice.needs_upload), (build.id, False))
        self.assertIn((build.id, f"{build.id} (your local build)"), choice.options)


class TestBuildsInTheClient(BuildsTest):
    def setUp(self):
        super().setUp()
        self.central = Central(scripts=DEMO_SCRIPTS)
        self.addCleanup(self.central.close)
        token = self.central.token("user", "laptop", "ann@example.com")
        self.remote = client.CentralClient(
            "http://server", token, session=HttpSession(self.central.app.test_client()))
        repo = self.tmp / "clone"
        for path, text in DEMO_SCRIPTS.items():
            (repo / "rvts" / path).parent.mkdir(parents=True, exist_ok=True)
            (repo / "rvts" / path).write_text(text)
        gitutil.create_repo(repo)
        self.branch = next(iter(find_worktrees(repo)))
        with closing(connect(self.tmp / "client.db")) as conn:
            init_db(conn)
        (self.tmp / "reports").mkdir()
        self.http = create_app(DB_PATH=self.tmp / "client.db", WORKSPACE_PATH=repo,
                               REPORTS_PATH=self.tmp / "reports", CENTRAL=self.remote,
                               TESTING=True).test_client()

    def view(self):
        return self.http.get(f"/workspace/{self.branch}/view?path=demo/tc.rst").get_data(True)

    def test_a_new_local_build_is_offered_uploaded_and_used(self):
        self.assertNotIn("New local build", self.view())
        build = self.make_build()
        page = self.view()
        self.assertIn("New local build", page)
        self.assertIn(f"upload your local build ({build.id})", page)

        response = self.http.post("/scratch/run", data={
            "workspace": self.branch, "script": "demo/tc.rst", "version-demo": "upload"})
        self.assertEqual(response.status_code, 302, response.get_data(True))
        self.assertTrue((self.build_repo / build.id / "demo.bin").is_file())
        (run,) = models.scratch_runs(self.central.reports)
        self.assertEqual(run["uut_versions"]["demo"]["id"], build.id)
        self.assertEqual(builds.last_used("demo"), build.id)

        page = self.view()
        self.assertNotIn("New local build", page)
        self.assertIn(f"{build.id} (your local build, last used)", page)

    def test_the_cli_uses_and_lists_local_builds(self):
        from automationv3 import cli
        import io
        from contextlib import redirect_stdout
        client.remember("http://server", self.remote.token, "ann@example.com")
        build = self.make_build(b"build 2")
        with mock.patch.object(client.requests, "Session",
                               lambda: HttpSession(self.central.app.test_client())):
            out = io.StringIO()
            with redirect_stdout(out):
                code = cli.list_builds(client.CentralClient.signed_in())
            self.assertEqual(code, 0)
            self.assertIn(f"demo: {build.id}", out.getvalue())
            self.assertIn("not uploaded yet", out.getvalue())
            with redirect_stdout(io.StringIO()):
                versions = cli.local_versions(client.CentralClient.signed_in(),
                                              {"demo": "local"})
            self.assertEqual(versions, {"demo": build.id})
            out = io.StringIO()
            with redirect_stdout(out):
                cli.list_builds(client.CentralClient.signed_in())
            self.assertIn(f"uploaded as {build.id}", out.getvalue())


class TestUploadedBuildsAreForScratch(BuildsTest):
    def test_reports_dont_offer_or_take_uploaded_builds(self):
        from automationv3.framework.planning import build_plan
        build = self.make_build()
        Demo().upload_build(build)
        server = Central(scripts=DEMO_SCRIPTS)
        self.addCleanup(server.close)
        root = server.gitdir / "rvts"
        report = build_plan("", root, ["demo/tc.rst"], versions={"demo": build.id})
        self.assertNotIn(build.id, report.uut_choices["demo"])
        self.assertIn(f"UUT demo has no version {build.id}", report.errors)
        scratch = build_plan("", root, ["demo/tc.rst"], versions={"demo": build.id},
                             scratch=True)
        self.assertEqual(scratch.errors, [])
        self.assertEqual(scratch.uut_versions["demo"]["id"], build.id)
