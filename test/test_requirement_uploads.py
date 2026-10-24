import base64
import io
import os
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from automationv3 import cli
from automationv3.services import client
from automationv3.services.requirements import export, models

from .central import SCRIPTS, Central, HttpSession
from .test_requirement_store import SRS, SYS, ExportCase


class TestImportsOnTheServer(ExportCase):
    def setUp(self):
        super().setUp()
        self.server = Central(scripts=SCRIPTS)
        self.addCleanup(self.server.close)
        self.folder = self.write([("SYS", None, {"index.rst": SYS}),
                                  ("SRS", None, {"index.rst": SRS})])

    def zipped(self):
        return export.zip_folder(self.folder)

    def test_admins_upload_a_zipped_export(self):
        ann = self.server.client("ann@example.com")
        page = ann.get("/requirements/imports").get_data(as_text=True)
        self.assertNotIn('type="file"', page)
        upload = {"export": (io.BytesIO(self.zipped()), "export.zip")}
        self.assertEqual(ann.post("/requirements/imports", data=upload,
                                  content_type="multipart/form-data").status_code, 403)

        lead = self.server.client("lead@example.com")
        self.assertIn('type="file"', lead.get("/requirements/imports").get_data(as_text=True))
        upload = {"export": (io.BytesIO(self.zipped()), "export.zip")}
        response = lead.post("/requirements/imports", data=upload,
                             content_type="multipart/form-data")
        self.assertEqual(response.status_code, 200, response.get_data(True))
        page = response.get_data(as_text=True)
        self.assertIn("Import #1", page)
        self.assertIn("by lead@example.com", page)
        with self.server.conn() as conn:
            self.assertEqual(models.importers(conn), {1: "lead@example.com"})
            self.assertIsNotNone(models.find_by_id(conn, "SW-1"))

    def test_a_zip_with_its_export_in_a_folder(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as archive:
            for file in self.folder.rglob("*"):
                if file.is_file():
                    archive.write(file, f"top/{file.relative_to(self.folder).as_posix()}")
        found = export.read_zip(out.getvalue(), "nested.zip")
        self.assertEqual(found.path, "nested.zip")
        self.assertEqual({s.key for s in found.specs}, {"SYS", "SRS"})

    def test_bad_uploads(self):
        with self.assertRaisesRegex(export.ExportError, "isn't a zip"):
            export.read_zip(b"nope")
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as archive:
            archive.writestr("../evil.txt", "x")
        with self.assertRaisesRegex(export.ExportError, "outside"):
            export.read_zip(out.getvalue())

    def test_requirements_import_with_server(self):
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        with mock.patch.dict(os.environ, {"AUTOMATION_CONFIG_HOME": home.name}), \
                mock.patch.object(client.requests, "Session",
                                  lambda: HttpSession(self.server.app.test_client())):
            client.remember("http://server",
                            self.server.token("user", "laptop", "ann@example.com"),
                            "ann@example.com")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cli.requirements(cli_args(self.folder)), 1)
            self.assertIn("Only admins", out.getvalue())

            client.remember("http://server",
                            self.server.token("user", "laptop", "lead@example.com"),
                            "lead@example.com")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cli.requirements(cli_args(self.folder)), 0)
            self.assertIn("Import 1:", out.getvalue())


def cli_args(folder):
    from docopt import docopt
    return docopt(cli.__doc__, argv=["requirements", "import", str(folder),
                                     "--server", "http://server"])


class TestReviewsRecordWho(unittest.TestCase):
    def test_review_by(self):
        from automationv3.services.database import connect, init_db
        from automationv3.services.requirements import suspects
        from automationv3.framework.requirement import Requirement
        conn = connect(":memory:")
        init_db(conn)
        models.insert(conn, [Requirement("R1", "It shall.")])
        suspects.review_script(conn, "master", "a.rst", "R1", "trunk", by="ann@example.com")
        (by,) = conn.execute("SELECT reviewed_by FROM script_reviews").fetchone()
        self.assertEqual(by, "ann@example.com")
        conn.close()
