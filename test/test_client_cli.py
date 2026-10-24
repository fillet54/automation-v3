import io
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from automationv3 import cli
from automationv3.services import client
from automationv3.services.worker import Host, Worker
from automationv3.services.worker.local import LocalServer

from .central import SCRIPTS, Central, HttpSession, link_path, sent_links
from .rvt import doc, rvt


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.server = Central(scripts=SCRIPTS)
        self.home = tempfile.TemporaryDirectory()
        env = mock.patch.dict(os.environ, {"AUTOMATION_CONFIG_HOME": self.home.name})
        env.start()
        self.addCleanup(env.stop)
        session = mock.patch.object(client.requests, "Session",
                                    lambda: HttpSession(self.server.app.test_client()))
        session.start()
        self.addCleanup(session.stop)

    def tearDown(self):
        self.server.close()
        self.home.cleanup()

    def sign_in(self, email="ann@example.com"):
        client.remember("http://server", self.server.token("user", "laptop", email), email)

    def cli(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            try:
                cli.main(list(argv))
            except SystemExit as e:
                code = e.code
        return code, out.getvalue()


class TestLogin(ClientTest):
    def test_login_by_emailed_link(self):
        central = client.CentralClient("server")
        browser = self.server.client()

        def approve(seconds):  # the person opens the link while the client waits
            (_, link, _), = sent
            browser.post(link_path(link))

        with sent_links() as sent:
            email = central.login("ann@example.com", device="ann-laptop", wait=approve,
                                  say=lambda *a: None)
        self.assertEqual(email, "ann@example.com")
        server, token, saved = client.signed_in()
        self.assertEqual((server, saved), ("http://server", "ann@example.com"))
        mode = stat.S_IMODE(os.stat(client.credentials_path()).st_mode)
        self.assertEqual(mode, 0o600)
        self.assertEqual(self.cli("whoami")[1].strip(), "ann@example.com on http://server")

    def test_logout_revokes_the_token(self):
        self.sign_in()
        _, token, _ = client.signed_in()
        self.assertEqual(self.cli("logout")[0], 0)
        with self.assertRaises(client.ClientError):
            client.signed_in()
        with self.assertRaisesRegex(client.ClientError, "doesn't know this machine"):
            client.CentralClient("http://server", token).whoami()

    def test_not_signed_in(self):
        code, out = self.cli("whoami")
        self.assertEqual(code, 2)
        self.assertIn("automation-v3 login --server", out)


class TestScratch(ClientTest):
    def setUp(self):
        super().setUp()
        self.sign_in()
        self.worktree = Path(self.home.name) / "worktree"
        for path, text in SCRIPTS.items():
            (self.worktree / path).parent.mkdir(parents=True, exist_ok=True)
            (self.worktree / path).write_text(text)
        # Edited, never committed or pushed
        (self.worktree / "plain/pass.rst").write_text(doc("Edited", rvt("(Wait 1) (Verify 2 = 3)")))

    def worker(self):
        worker = Worker(LocalServer(self.server.db, self.server.reports, "local://w"), Host())
        worker.check_in(started=True)
        return worker

    def test_scratch_uploads_the_worktree_and_waits(self):
        worker = self.worker()
        waits = mock.patch("automationv3.services.client.time.sleep",
                           lambda s: worker.work_once())
        with waits:
            code, out = self.cli("scratch", "plain/pass.rst", "--root", str(self.worktree))
        self.assertEqual(code, 1, out)
        self.assertIn("Queued plain/pass.rst: http://", out)
        self.assertIn("FAIL", out)
        self.assertIn("fail     plain/pass.rst", out)

    def test_no_wait(self):
        code, out = self.cli("scratch", "plain/fail.rst", "--root", str(self.worktree),
                             "--no-wait")
        self.assertEqual(code, 0)
        self.assertIn("/reports/scratch/runs/", out)

    def test_a_broken_script_is_reported_before_uploading(self):
        (self.worktree / "plain/bad.rst").write_text(rvt("(Nope 1)"))
        code, out = self.cli("scratch", "plain/bad.rst", "--root", str(self.worktree))
        self.assertEqual(code, 2)
        self.assertIn("plain/bad.rst", out)
