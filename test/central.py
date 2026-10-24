"""A central server for tests: accounts on, a git workspace of the sample
scripts, and helpers to sign people in"""

import re
import shutil
import tempfile
from contextlib import closing, contextmanager
from pathlib import Path
from unittest import mock

from automationv3.services import accounts
from automationv3.services.database import connect, init_db
from automationv3.services.settings import Auth, Settings
from automationv3.services.workspace import find_worktrees
from automationv3.web.app import create_app
from automationv3.web.auth import COOKIE

from .data import make_workspaces as gitutil

RVTS = Path(__file__).resolve().parent / "data" / "rvts"

AUTH = Auth(allowed_domains=("example.com",), admins=("lead@example.com",))


class Central:
    def __init__(self, settings=None, scripts=RVTS, **config):
        self.tmp = Path(tempfile.mkdtemp())
        self.gitdir = self.tmp / "repo"
        shutil.copytree(scripts, self.gitdir / "rvts")
        gitutil.create_repo(self.gitdir)
        self.branch = next(iter(find_worktrees(self.gitdir)))
        self.db = self.tmp / "test.db"
        self.reports = self.tmp / "reports"
        self.reports.mkdir()
        with closing(connect(self.db)) as conn:
            init_db(conn)
        self.settings = settings or Settings(auth=AUTH)
        self.app = create_app(DB_PATH=self.db, REPORTS_PATH=self.reports,
                              WORKSPACE_PATH=self.gitdir, TESTING=True,
                              SETTINGS=self.settings, **config)

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @contextmanager
    def conn(self):
        with closing(connect(self.db)) as conn:
            yield conn

    def user(self, email):
        with self.conn() as conn:
            return accounts.ensure_user(conn, email)

    def client(self, email=None):
        """A test client, signed in as `email` if given"""
        client = self.app.test_client()
        if email:
            with self.conn() as conn:
                user = accounts.ensure_user(conn, email)
                token = accounts.create_session(conn, user, 30)
            client.set_cookie(COOKIE, token)
        return client

    def token(self, kind, name, email=None):
        """A new API token's secret: a user's device, or a worker's"""
        with self.conn() as conn:
            user = accounts.ensure_user(conn, email) if email else None
            return accounts.create_token(conn, kind, name, user=user if kind == "user" else None,
                                         created_by=user if kind == "worker" else None)


@contextmanager
def sent_links():
    """Captures the sign-in links the server emails: [(to, link, device)]"""
    sent = []

    def send(smtp, to, link, minutes, device=None, brand=""):
        sent.append((to, link, device))
        return True

    with mock.patch("automationv3.services.mail.send_sign_in", send):
        yield sent


def link_path(link):
    """The path of an emailed link, for the test client"""
    return re.sub(r"^https?://[^/]+", "", link)
