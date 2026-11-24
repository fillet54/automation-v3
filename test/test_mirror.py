import hashlib
import hmac
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from automationv3.services.mirror import MirrorError, MirrorWorkspaces
from automationv3.services.reports import store
from automationv3.services.settings import Git, Settings

from .central import AUTH, SCRIPTS, Central
from .rvt import doc, rvt


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


class TestMirror(unittest.TestCase):
    """A central server mirroring a remote: the team's repository"""

    def setUp(self):
        # The remote is an ordinary repository; Central's own repo is unused
        self.server = Central(settings=Settings(auth=AUTH, git=Git(
            remote="placeholder", webhook_secret="s3cret")), scripts=SCRIPTS)
        self.remote = self.server.gitdir
        mirror = MirrorWorkspaces(str(self.remote), self.server.tmp / "mirror.git",
                                  self.server.tmp / "checked-in", scripts="rvts")
        self.server.app.config["WORKSPACES"] = mirror
        mirror.refresh()
        self.mirror = mirror
        self.ann = self.server.client("ann@example.com")

    def tearDown(self):
        self.server.close()

    def push(self, branch, path, text):
        """A commit on `branch` of the remote (checked out there)"""
        if branch not in git(self.remote, "branch", "--format=%(refname:short)").split():
            git(self.remote, "checkout", "-q", "-b", branch)
        else:
            git(self.remote, "checkout", "-q", branch)
        (self.remote / "rvts" / path).parent.mkdir(parents=True, exist_ok=True)
        (self.remote / "rvts" / path).write_text(text)
        git(self.remote, "add", "-A")
        git(self.remote, "-c", "user.name=t", "-c", "user.email=t@example.com",
            "commit", "-q", "-m", f"{path} on {branch}")
        return git(self.remote, "rev-parse", "HEAD")

    def hook(self, body=b"{}", **headers):
        return self.server.client().post("/hooks/git", data=body, headers=headers)

    def github(self, body=b'{"ref": "refs/heads/x"}', secret="s3cret"):
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return self.hook(body, **{"X-Hub-Signature-256": f"sha256={signature}"})

    def test_branches_are_the_remotes_at_their_tips(self):
        (name,) = self.mirror.branches()
        root = self.mirror.root(name)
        self.assertTrue((root / "plain" / "pass.rst").is_file())
        self.assertEqual(self.mirror.edited(name), set())
        self.assertEqual(self.mirror.checked_in(name), root)
        self.assertIn("Passes", self.mirror.committed_text(name, "plain/pass.rst"))
        page = self.ann.get(f"/workspace/{name}").get_data(as_text=True)
        self.assertIn(name, page)

    def test_a_signed_webhook_fetches(self):
        self.push("feature", "plain/new.rst", doc("New", rvt("(Wait 1)")))
        self.assertNotIn("feature", self.mirror.branches())
        self.assertEqual(self.github(secret="wrong").status_code, 403)
        self.assertEqual(self.hook().status_code, 403)
        self.assertNotIn("feature", self.mirror.branches())

        response = self.github()
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertIn("feature", self.mirror.branches())

    def test_gitlab_and_gitea_webhooks(self):
        self.assertEqual(self.hook(**{"X-Gitlab-Token": "s3cret"}).status_code, 200)
        self.assertEqual(self.hook(**{"X-Gitlab-Token": "nope"}).status_code, 403)
        body = b"{}"
        sig = hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
        self.assertEqual(self.hook(body, **{"X-Gitea-Signature": sig}).status_code, 200)

    def test_queuing_a_report_fetches_first_and_records_the_commit(self):
        branch = next(iter(self.mirror.branches()))
        commit = self.push(branch, "plain/pass.rst", doc("Passes, again", rvt("(Wait 2)")))
        # No webhook came: queuing fetches anyway
        response = self.ann.post("/runner/queue", data={"workspace": branch,
                                                        "script": "plain/pass.rst"})
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
        report_id = response.headers["Location"].rsplit("/", 1)[1]
        report = store.load_report(self.server.reports, report_id)
        self.assertEqual(report["additions"][0]["commit"], commit)
        (run,) = store.list_runs(self.server.reports, report_id)
        self.assertEqual(run["commit"], commit)
        closure = store.read_closure(self.server.reports, report_id, run["id"])
        self.assertIn("(Wait 2)", closure["plain/pass.rst"])


class TestWebhookOff(unittest.TestCase):
    def test_a_server_without_a_mirror_has_no_webhook(self):
        server = Central(scripts=SCRIPTS)
        try:
            self.assertEqual(server.client().post("/hooks/git").status_code, 404)
        finally:
            server.close()


class TestMirrorScriptsFolder(unittest.TestCase):
    """The mirror shows the [git] scripts folder of each branch"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.remote = self.tmp / "remote"
        (self.remote / "tests" / "scripts").mkdir(parents=True)
        (self.remote / "tests" / "scripts" / "a.rst").write_text("(Wait 1)")
        (self.remote / "README").write_text("top")
        for args in (["init", "-q", "-b", "master"], ["add", "--all"],
                     ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "one"]):
            subprocess.run(["git", *args], cwd=self.remote, check=True)

    def mirror(self, scripts):
        mirror = MirrorWorkspaces(str(self.remote), self.tmp / f"m-{scripts or 'top'}.git",
                                  self.tmp / f"c-{scripts or 'top'}", scripts=scripts)
        mirror.refresh()
        return mirror

    def test_a_folder_below_the_top(self):
        mirror = self.mirror("tests/scripts")
        self.assertEqual(sorted(p.name for p in mirror.root("master").iterdir()), ["a.rst"])
        self.assertEqual(mirror.committed_text("master", "a.rst"), "(Wait 1)")

    def test_the_top(self):
        mirror = self.mirror("")
        self.assertEqual(sorted(p.name for p in mirror.root("master").iterdir()), ["README", "tests"])
        self.assertEqual(mirror.committed_text("master", "tests/scripts/a.rst"), "(Wait 1)")

    def test_a_branch_without_the_folder_is_left_out(self):
        self.assertEqual(self.mirror("elsewhere").branches(), {})

    def test_a_failed_extract_is_not_remembered_as_empty(self):
        mirror = self.mirror("tests/scripts")
        missing = "0" * 40  # not fetched (yet): says nothing about its scripts folder
        with self.assertRaises(MirrorError):
            mirror.extract(missing)
        self.assertEqual(list(mirror.cache.glob(f"{missing}*")), [])
        self.assertEqual(sorted(p.name for p in mirror.root("master").iterdir()), ["a.rst"])
