"""Requirements from a CSV or a list, in every mode: on this machine with
no central server, uploaded to a central server, and the local client
reading them from it"""

import base64
import io
import os
import shutil
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path
from unittest import mock

from docopt import docopt

from automationv3 import cli
from automationv3.services import client
from automationv3.services.database import connect, init_db
from automationv3.services.requirements import export, flat, models, rst_source
from automationv3.web.app import create_app

from .central import SCRIPTS, Central, HttpSession

CSV = (b"\xef\xbb\xbfID,Text,Satisfies,Subsystem,Section,Verification Method\n"
       b'SRS-1,"The VM shall *shed* loads below 40%:\n- the payload first",SYS-1,EPS,Power,Test\n'
       b"SRS-2,The VM shall keep time.,,TIM,,\n")
LIST = b"# The SRS, by hand\nSRS-1  The VM shall shed loads.\n\nSRS-2: The VM shall keep time.\n"


def texts(found):
    return {r.id: rst_source.plain_text(r.text) for r in found.specs[0].requirements}


class TestReading(unittest.TestCase):
    def test_a_csv(self):
        found = flat.read(CSV, "srs.csv", "SRS", parents=["SYS"])
        (spec,) = found.specs
        self.assertEqual((spec.key, spec.level, spec.parents, spec.baseline),
                         ("SRS", "software", ["SYS"], None))
        self.assertEqual(set(spec.attributes), {"subsystem", "verification-method"})
        one, two = sorted(spec.requirements, key=lambda r: r.id)
        # The text is as written: rst markup characters don't count
        self.assertEqual(rst_source.plain_text(one.text),
                         "The VM shall *shed* loads below 40%: - the payload first")
        self.assertEqual(one.satisfies, ("SYS-1",))
        self.assertEqual(one.section, ("SRS", "Power"))
        self.assertEqual(one.attributes, {"subsystem": "EPS", "verification-method": "Test"})
        self.assertEqual(two.attributes, {"subsystem": "TIM"})
        self.assertIsNotNone(found.exported_at)

    def test_a_list(self):
        self.assertEqual(texts(flat.read(LIST, "srs.txt", "SRS")),
                         {"SRS-1": "The VM shall shed loads.",
                          "SRS-2": "The VM shall keep time."})

    def test_a_tsv(self):
        found = flat.read(b"id\ttext\nA-1\tIt shall, with commas.\n", "a.tsv", "A")
        self.assertEqual(texts(found), {"A-1": "It shall, with commas."})

    def test_every_problem_is_named(self):
        with self.assertRaises(export.ExportError) as e:
            flat.read(b"id,text\nX,\nX,y\nbad id,z\n,w\n", "b.csv", "S")
        self.assertEqual(str(e.exception).splitlines(), [
            "b.csv:2: X has no text", "b.csv:3: X is also on line 2",
            "b.csv:4: id 'bad id' can't have spaces or commas", "b.csv:5: no id"])
        for data, name, message in [
                (b"name,txt\n", "c.csv", "which column holds each requirement.s id"),
                (b"A-1\n", "d.txt", "A-1 has no text"),
                (b"\xff\xfe", "e.csv", "isn't UTF-8"),
                (b"# nothing\n", "f.txt", "holds no requirements")]:
            with self.assertRaisesRegex(export.ExportError, message):
                flat.read(data, name, "S")
        with self.assertRaisesRegex(export.ExportError, "name the spec"):
            flat.read(LIST, "srs.txt", "")
        with self.assertRaisesRegex(export.ExportError, "zipped export folder"):
            export.read_upload(b"x", "srs.pdf", spec="SRS")

    def test_reimporting_gives_history(self):
        conn = connect(":memory:")
        init_db(conn)
        from automationv3.services.requirements import store
        store.import_export(conn, flat.read(LIST, "srs.txt", "SRS"))
        _, outcomes = store.import_export(conn, flat.read(LIST, "srs.txt", "SRS"))
        self.assertIn("unchanged", outcomes[0][1])
        changed = LIST.replace(b"shed loads.", b"shed loads in order.")
        store.import_export(conn, flat.read(changed.replace(b"SRS-2: The VM shall keep time.\n", b""),
                                            "srs.txt", "SRS"))
        changes = {c.id: c.changes for c in models.diff(conn, "trunk@1", "trunk@3")}
        self.assertEqual(set(changes), {"SRS-1", "SRS-2"})
        self.assertIn("text", changes["SRS-1"])
        self.assertIsNone(models.find_by_id(conn, "SRS-2"))
        conn.close()


def args(*argv):
    return docopt(cli.__doc__, argv=["requirements", "import", *argv])


class TestWithoutACentralServer(unittest.TestCase):
    """automation-v3 server on its own: the CLI and the Imports page write
    this machine's database"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = self.tmp / "automationv3.db"
        (self.tmp / "srs.csv").write_bytes(CSV)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_cli(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            status = cli.requirements(args(*argv, "--dbpath", str(self.db)))
        return status, out.getvalue()

    def test_the_cli(self):
        status, out = self.run_cli(str(self.tmp / "srs.csv"))
        self.assertEqual(status, 1)
        self.assertIn("say which spec it is with --spec", out)
        status, out = self.run_cli(str(self.tmp / "srs.csv"), "--spec", "SRS",
                                   "--title", "Vehicle Manager SRS")
        self.assertEqual(status, 0, out)
        self.assertIn("SRS (trunk)", out)
        status, out = self.run_cli(str(self.tmp / "srs.csv"), "--spec", "SRS",
                                   "--baseline", "1.0")
        self.assertEqual(status, 0, out)
        with closing(connect(self.db)) as conn:
            self.assertEqual(models.find_by_id(conn, "SRS-2").subsystem, "TIM")
            self.assertIsNotNone(models.find_by_id(conn, "SRS-1", "SRS@1.0"))
            self.assertEqual(models.specs(conn)[0].title, "Vehicle Manager SRS")

    def test_the_imports_page(self):
        with closing(connect(self.db)) as conn:
            init_db(conn)
        app = create_app(DB_PATH=str(self.db), TESTING=True)
        http = app.test_client()
        page = http.get("/requirements/imports").get_data(as_text=True)
        self.assertIn('accept=".xlsx,.csv,.tsv,.txt,.list,.zip"', page)
        # A form naming the spec imports straight away, as the API does
        response = http.post("/requirements/imports", content_type="multipart/form-data",
                             data={"export": (io.BytesIO(LIST), "srs.txt"), "spec": "SRS",
                                   "level": "software", "parents": ""})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertIn("Import #1", response.get_data(as_text=True))
        page = http.get("/requirements/req/SRS-1").get_data(as_text=True)
        self.assertIn("shed loads.", page)


class TestOnACentralServer(unittest.TestCase):
    def setUp(self):
        self.server = Central(scripts=SCRIPTS)
        self.addCleanup(self.server.close)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        (self.tmp / "srs.txt").write_bytes(LIST)

    def test_admins_upload_a_csv(self):
        def upload():
            return {"export": (io.BytesIO(CSV), "srs.csv"), "spec": "SRS", "parents": "SYS"}
        ann = self.server.client("ann@example.com")
        self.assertEqual(ann.post("/requirements/imports", data=upload(),
                                  content_type="multipart/form-data").status_code, 403)
        lead = self.server.client("lead@example.com")
        response = lead.post("/requirements/imports", data=upload(),
                             content_type="multipart/form-data")
        self.assertEqual(response.status_code, 200, response.get_data(True))
        self.assertIn("by lead@example.com", response.get_data(as_text=True))
        with self.server.conn() as conn:
            self.assertEqual(models.find_by_id(conn, "SRS-1").subsystem, "EPS")

    def test_the_api(self):
        lead = self.server.client("lead@example.com")
        token = self.server.token("user", "laptop", "lead@example.com")
        response = lead.post("/api/requirements/import",
                             headers={"Authorization": f"Bearer {token}"},
                             json={"file": base64.b64encode(LIST).decode(),
                                   "name": "srs.txt", "spec": "SRS", "baseline": "2"})
        self.assertEqual(response.status_code, 201, response.get_data(True))
        self.assertEqual(response.get_json()["outcomes"][0][0], "SRS@2")

    def test_the_cli_uploads(self):
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        with mock.patch.dict(os.environ, {"AUTOMATION_CONFIG_HOME": home.name}), \
                mock.patch.object(client.requests, "Session",
                                  lambda: HttpSession(self.server.app.test_client())):
            client.remember("http://server",
                            self.server.token("user", "laptop", "lead@example.com"),
                            "lead@example.com")
            out = io.StringIO()
            with redirect_stdout(out):
                status = cli.requirements(args(str(self.tmp / "srs.txt"), "--spec", "SRS",
                                               "--server", "http://server"))
            self.assertEqual(status, 0, out.getvalue())
            self.assertIn("SRS (trunk)", out.getvalue())
            out = io.StringIO()
            with redirect_stdout(out):
                status = cli.requirements(args(str(self.tmp / "srs.txt"),
                                               "--server", "http://server"))
            self.assertEqual(status, 1)
            self.assertIn("--spec", out.getvalue())
        with self.server.conn() as conn:
            self.assertIsNotNone(models.find_by_id(conn, "SRS-2"))


class TestTheLocalClient(unittest.TestCase):
    """automation-v3 client keeps no requirements: its requirement pages
    are the central server's"""

    def test_requirement_pages_go_to_the_central_server(self):
        server = Central(scripts=SCRIPTS)
        self.addCleanup(server.close)
        token = server.token("user", "laptop", "ann@example.com")
        remote = client.CentralClient("http://server", token,
                                      session=HttpSession(server.app.test_client()))
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        app = create_app(DB_PATH=str(tmp / "client.db"), WORKSPACE_PATH=str(tmp),
                         CENTRAL=remote, TESTING=True)
        http = app.test_client()
        for path in ("/requirements/imports", "/requirements/req/SRS-1?context=trunk"):
            response = http.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertEqual(response.headers["Location"], "http://server" + path)
        response = http.post("/requirements/imports", data={})
        self.assertEqual(response.status_code, 302)


if __name__ == "__main__":
    unittest.main()


def workbook(rows, sheets=("Requirements",)):
    """An .xlsx with `rows` on its last sheet, and empty sheets before it"""
    import openpyxl
    book = openpyxl.Workbook()
    book.active.title = sheets[0]
    for name in sheets[1:]:
        book.create_sheet(name)
    for row in rows:
        book[sheets[-1]].append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


DOORS_LIKE = [["Object Identifier", "Object Text", "Parent Requirements", "Verification Method",
               "Allocation", "Notes"],
              ["VM-1", "The VM shall boot.", "SYS-1; SYS-2", "Test", "CPU", "x"],
              ["VM-2", "The VM shall log.", None, "Analysis", 3.0, None],
              [None, None, None, None, None, None]]


class TestColumns(unittest.TestCase):
    def test_columns_are_guessed_from_their_headers(self):
        columns = flat.guess([h for h in DOORS_LIKE[0]])
        self.assertEqual((columns.id, columns.text, columns.satisfies, columns.section),
                         (0, 1, 2, None))
        self.assertEqual(columns.attributes, {3: "verification-method", 4: "allocation",
                                              5: "notes"})

    def test_a_workbook(self):
        data = workbook(DOORS_LIKE, sheets=("Cover", "Requirements"))
        table = flat.table(data, "vm.xlsx")
        # The first sheet with something on it, not the blank cover
        self.assertEqual((table.sheets, table.sheet),
                         (["Cover", "Requirements"], "Requirements"))
        with self.assertRaisesRegex(export.ExportError, "is empty"):
            flat.read(data, "vm.xlsx", "VM", sheet="Cover")
        with self.assertRaisesRegex(export.ExportError, "has no sheet 'Nope'"):
            flat.read(data, "vm.xlsx", "VM", sheet="Nope")
        columns = flat.guess(DOORS_LIKE[0])
        del columns.attributes[5]  # Notes, ignored
        found = flat.read(data, "vm.xlsx", "VM", sheet="Requirements", columns=columns)
        one, two = found.specs[0].requirements
        self.assertEqual(one.satisfies, ("SYS-1", "SYS-2"))
        self.assertEqual(two.attributes, {"allocation": "3", "verification-method": "Analysis"})
        source = found.manifest["specs"][0]["source"]
        self.assertEqual(source["sheet"], "Requirements")
        self.assertEqual(source["columns"]["id"], "Object Identifier")
        self.assertNotIn("Notes", source["columns"]["attributes"])

    def test_columns_kept_by_header_survive_reordering(self):
        columns = flat.guess(DOORS_LIKE[0])
        saved = columns.by_header(DOORS_LIKE[0])
        moved = ["Notes", "Object Text", "Object Identifier", "Allocation"]
        again = flat.Columns.from_headers(saved, moved)
        self.assertEqual((again.id, again.text, again.satisfies), (2, 1, None))
        self.assertEqual(again.attributes, {0: "notes", 3: "allocation"})

    def test_bad_columns(self):
        data = b"a,b,c,d\nX,y,1,2\n"
        with self.assertRaisesRegex(export.ExportError, "two columns are attribute 'n'"):
            flat.read(data, "s.csv", "S",
                      columns=flat.Columns(id=0, text=1, attributes={2: "n", 3: "n"}))
        with self.assertRaisesRegex(export.ExportError, "only one role"):
            flat.read(data, "s.csv", "S", columns=flat.Columns(id=0, text=0))
        with self.assertRaisesRegex(export.ExportError, "each requirement's text"):
            flat.read(data, "s.csv", "S", columns=flat.Columns(id=0))


class TestTheSheetImportPage(unittest.TestCase):
    """Upload, match columns, preview, import: on a server of its own"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.db = self.tmp / "automationv3.db"
        with closing(connect(self.db)) as conn:
            init_db(conn)
        self.http = create_app(DB_PATH=str(self.db), TESTING=True).test_client()

    def upload(self, data, name):
        response = self.http.post("/requirements/imports", content_type="multipart/form-data",
                                  data={"export": (io.BytesIO(data), name)})
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
        return response.headers["Location"]

    def page(self, url, **params):
        response = self.http.get(url, query_string=params)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_data(as_text=True)

    def test_upload_preview_import(self):
        rows = [["Req ID", "Requirement", "Section", "Owner"],
                ["SRS-1", "The VM shall boot.", "Start", "ann"],
                ["SRS-2", "The VM shall log.", "", "bob"]]
        url = self.upload(workbook(rows), "srs.xlsx")
        self.assertIn("/requirements/imports/sheet/", url)
        page = self.page(url)
        self.assertIn("Req ID", page)
        self.assertIn('<option value="id" selected>', page)
        self.assertNotIn("What importing does", page)

        choices = {"spec": "SRS", "title": "", "baseline": "", "level": "software",
                   "parents": "", "sheet": "Requirements", "role_0": "id", "role_1": "text",
                   "role_2": "section", "role_3": ""}
        page = self.page(url, **choices)
        self.assertIn("2 added", page)
        self.assertIn("a new spec", page)
        self.assertIn('name="role_3" value=""', page)  # carried to the import, ignored

        response = self.http.post(url, data=choices)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertIn("Import #1", response.get_data(as_text=True))
        with closing(connect(self.db)) as conn:
            self.assertEqual(models.find_by_id(conn, "SRS-1").section, ("SRS", "Start"))
            self.assertEqual(models.find_by_id(conn, "SRS-1").attributes, {})
        self.assertEqual(self.http.get(url).status_code, 404)  # the upload is gone

        # Next time: the same file name comes back as it was read, and the
        # preview says what changed
        rows[1][1] = "The VM shall boot in 5 s."
        del rows[2]
        rows.append(["SRS-3", "The VM shall stop.", "", ""])
        url = self.upload(workbook(rows), "srs.xlsx")
        page = self.page(url)
        self.assertIn("Filled in from the last import of srs.xlsx", page)
        self.assertIn('value="SRS"', page)
        page = self.page(url, **choices)
        for count in ("1 added", "1 changed", "1 removed", "0 unchanged"):
            self.assertIn(count, page)
        self.assertIn("boot<ins> in 5 s</ins>", page)

    def test_problems_are_shown_not_imported(self):
        url = self.upload(b"id,text\nA-1,\nA-1,again\n", "a.csv")
        page = self.page(url, spec="A", level="software", role_0="id", role_1="text")
        self.assertIn("Fix these before importing", page)
        self.assertIn("a.csv:2: A-1 has no text", page)
        self.assertNotIn("What importing does", page)
        page = self.page(url, spec="A", level="software", role_0="id", role_1="id")
        self.assertIn("Two columns are the id", page)

    def test_a_list(self):
        url = self.upload(LIST, "srs.txt")
        page = self.page(url)
        self.assertNotIn('name="role_0"', page)  # a list has no columns to match
        page = self.page(url, spec="SRS", level="software")
        self.assertIn("2 added", page)

    def test_a_changed_baseline_is_refused(self):
        url = self.upload(LIST, "srs.txt")
        self.http.post(url, data={"spec": "SRS", "baseline": "1", "level": "software"})
        url = self.upload(LIST.replace(b"shed", b"drop"), "srs.txt")
        page = self.page(url, spec="SRS", baseline="1", level="software")
        self.assertIn("This import would be refused", page)

    def test_only_admins_on_a_central_server(self):
        server = Central(scripts=SCRIPTS)
        self.addCleanup(server.close)
        ann = server.client("ann@example.com")
        response = ann.post("/requirements/imports", content_type="multipart/form-data",
                            data={"export": (io.BytesIO(LIST), "srs.txt")})
        self.assertEqual(response.status_code, 403)
        lead = server.client("lead@example.com")
        response = lead.post("/requirements/imports", content_type="multipart/form-data",
                             data={"export": (io.BytesIO(LIST), "srs.txt")})
        self.assertEqual(response.status_code, 302)
        url = response.headers["Location"]
        self.assertEqual(ann.get(url).status_code, 403)
        self.assertEqual(lead.get(url).status_code, 200)
        response = lead.post(url, data={"spec": "SRS", "level": "software"})
        self.assertIn("by lead@example.com", response.get_data(as_text=True))
