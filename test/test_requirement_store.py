"""Importing DOORS exports, and what the store says afterwards"""

import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from automationv3 import cli, demo
from automationv3.services.database import connect, init_db
from automationv3.services.requirements import export, models, store

SCHEMA = {"subsystem": {"type": "string"},
          "verification": {"type": "enum", "values": ["Test", "Analysis"]},
          "allocation": {"type": "list"},
          "modified-by": {"type": "string", "hashed": False}}

SYS = """System
======

.. requirement:: SYS-1
   :verification: Analysis

   The system shall work.
"""

SRS = """Software
========

Power
-----

.. requirement:: SW-1
   :satisfies: SYS-1
   :subsystem: EPS
   :verification: Test
   :modified-by: ann

   The software shall shed loads below 40%.

.. requirement:: SW-2
   :subsystem: EPS
   :allocation: B, A

   The software shall report the state of charge.

Time
----

.. requirement:: SW-3
   :satisfies: SYS-1
   :subsystem: TIM

   The software shall keep time.
"""


class ExportCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.n = 0
        self.conn = connect(":memory:")
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp)

    def write(self, specs, sets=(), **manifest):
        """An export folder holding `specs`: [(key, baseline, {path: text},
        extra manifest fields)]"""
        self.n += 1
        folder = self.tmp / f"export-{self.n}"
        entries = []
        for key, baseline, files, *extra in specs:
            root = f"{key}@{baseline}" if baseline else key
            for path, text in files.items():
                (folder / root / path).parent.mkdir(parents=True, exist_ok=True)
                (folder / root / path).write_text(text)
            level = "system" if key == "SYS" else "software"
            entries.append({"key": key, "title": key, "level": level, "root": root,
                            "parents": [] if key == "SYS" else ["SYS"],
                            "attributes": SCHEMA,
                            **({"baseline": baseline} if baseline else {}),
                            **(extra[0] if extra else {})})
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "manifest.json").write_text(json.dumps(
            {"format": 1, "specs": entries,
             "exported_at": f"2026-01-01T00:{self.n // 60:02d}:{self.n % 60:02d}Z",
             "baseline_sets": [{"name": n, "specs": p} for n, p in sets], **manifest}))
        return folder

    def load(self, specs, sets=()):
        return store.import_export(self.conn, export.read(self.write(specs, sets)))

    def trunk(self, sys=SYS, srs=SRS):
        return self.load([("SYS", None, {"index.rst": sys}), ("SRS", None, {"index.rst": srs})])


class TestReading(ExportCase):
    def test_reads_requirements_with_typed_attributes(self):
        e = export.read(self.write([("SRS", None, {"index.rst": SRS})]))
        sw1, sw2, sw3 = e.specs[0].requirements
        self.assertEqual(sw1.satisfies, ("SYS-1",))
        self.assertEqual(sw1.section, ("Software", "Power"))
        self.assertEqual(sw2.attributes["allocation"], ["A", "B"])
        self.assertEqual(sw3.section, ("Software", "Time"))

    def assertRefused(self, specs, message, **manifest):
        with self.assertRaises(export.ExportError) as e:
            export.read(self.write(specs, **manifest))
        self.assertIn(message, str(e.exception))

    def test_refuses_an_unknown_format(self):
        self.assertRefused([("SRS", None, {"index.rst": SRS})], "format 2", format=2)

    def test_refuses_attributes_not_in_the_schema(self):
        self.assertRefused([("SRS", None, {"index.rst": SRS.replace(":subsystem: TIM",
                                                                    ":subsytem: TIM")})],
                           "'subsytem' is not in the spec's schema")

    def test_refuses_enum_values_not_in_the_schema(self):
        self.assertRefused([("SRS", None, {"index.rst": SRS.replace("Test", "Guess")})],
                           "'Guess' is not one of Test, Analysis")

    def test_refuses_a_conf_py(self):
        self.assertRefused([("SRS", None, {"index.rst": SRS, "conf.py": ""})], "conf.py")

    def test_refuses_a_missing_index(self):
        self.assertRefused([("SRS", None, {"other.rst": SRS})], "index.rst is missing")

    def test_refuses_an_id_in_two_files(self):
        self.assertRefused([("SRS", None, {"index.rst": SRS, "more.rst": SRS})],
                           "SW-1 is defined twice")

    def test_refuses_an_id_in_two_trunk_specs(self):
        self.assertRefused([("SYS", None, {"index.rst": SYS}),
                            ("SRS", None, {"index.rst": SRS + "\n" + SYS})],
                           "SYS-1 is in both")

    def test_refuses_a_bad_level(self):
        self.assertRefused([("SRS", None, {"index.rst": SRS}, {"level": "module"})],
                           "level 'module'")


class TestHashing(ExportCase):
    def requirement(self, text):
        return export.read(self.write([("SRS", None, {"index.rst": text})])).specs[0].requirements[0]

    def test_markup_and_wrapping_are_not_changes(self):
        a = self.requirement(SRS)
        b = self.requirement(SRS.replace("The software shall shed loads below 40%.",
                                         "The *software* shall shed\n   loads below 40%."))
        self.assertEqual(a.text_hash, b.text_hash)
        self.assertNotEqual(a.hash, b.hash)

    def test_unhashed_attributes_are_not_changes(self):
        a = self.requirement(SRS)
        b = self.requirement(SRS.replace(":modified-by: ann", ":modified-by: bob"))
        self.assertEqual(a.metadata_hash, b.metadata_hash)

    def test_link_order_is_not_a_change(self):
        a = self.requirement(SRS.replace(":satisfies: SYS-1\n   :subsystem: EPS",
                                         ":satisfies: SYS-1, SYS-2\n   :subsystem: EPS"))
        b = self.requirement(SRS.replace(":satisfies: SYS-1\n   :subsystem: EPS",
                                         ":satisfies: SYS-2,SYS-1\n   :subsystem: EPS"))
        self.assertEqual(a.links_hash, b.links_hash)


class TestImporting(ExportCase):
    def test_first_trunk_adds_everything(self):
        _, outcomes = self.trunk()
        self.assertEqual(outcomes, [("SYS (trunk)", "new: 1 requirements"),
                                    ("SRS (trunk)", "new: 3 requirements")])
        self.assertEqual([r.id for r in models.find_all(self.conn)],
                         ["SW-1", "SW-2", "SW-3", "SYS-1"])

    def test_the_same_content_again_changes_nothing(self):
        self.trunk()
        _, outcomes = self.trunk()
        self.assertEqual([o for _, o in outcomes], ["unchanged", "unchanged"])
        self.assertEqual(models.log(self.conn)[0][3], [])

    def test_trunk_logs_each_change_and_what_changed(self):
        self.trunk()
        changed = (SRS.replace("below 40%", "below 45%")
                      .replace(":verification: Test\n", "")
                      .replace(".. requirement:: SW-2\n   :subsystem: EPS",
                               ".. requirement:: SW-2\n   :satisfies: SYS-1\n   :subsystem: EPS")
                      .replace("Time\n----\n\n", "")
                      .replace(".. requirement:: SW-1", ".. requirement:: SW-4\n\n"
                               "   The software shall be new.\n\n.. requirement:: SW-1"))
        _, outcomes = self.trunk(srs=changed.replace(
            ".. requirement:: SW-2", ".. requirement:: SW-2", 1))
        self.assertEqual(outcomes[1], ("SRS (trunk)", "1 added, 3 changed"))
        (_, _, _, changes), *_ = models.log(self.conn)
        self.assertEqual(changes, [("SRS", "SW-1", ("text", "metadata")),
                                   ("SRS", "SW-2", ("links",)),
                                   ("SRS", "SW-3", ("section",)),
                                   ("SRS", "SW-4", ("added",))])

    def test_removing_a_requirement_is_logged(self):
        self.trunk()
        self.trunk(srs=SRS.split("Time\n")[0])
        (_, _, _, changes), *_ = models.log(self.conn)
        self.assertEqual(changes, [("SRS", "SW-3", ("removed",))])

    def test_trunk_only_moves_forward(self):
        older = self.write([("SRS", None, {"index.rst": SRS})])
        self.trunk()
        with self.assertRaises(store.ImportError_) as e:
            store.import_export(self.conn, export.read(older))
        self.assertIn("trunk only moves forward", str(e.exception))

    def test_the_same_export_twice_is_unchanged_but_not_new_content(self):
        folder = self.write([("SRS", None, {"index.rst": SRS})])
        store.import_export(self.conn, export.read(folder))
        _, outcomes = store.import_export(self.conn, export.read(folder))
        self.assertEqual(outcomes, [("SRS (trunk)", "unchanged")])
        (folder / "SRS" / "index.rst").write_text(SRS.replace("40%", "45%"))
        with self.assertRaises(store.ImportError_):
            store.import_export(self.conn, export.read(folder))

    def test_trunk_needs_an_export_time(self):
        folder = self.write([("SRS", None, {"index.rst": SRS})])
        manifest = json.loads((folder / "manifest.json").read_text())
        del manifest["exported_at"]
        (folder / "manifest.json").write_text(json.dumps(manifest))
        with self.assertRaises(export.ExportError):
            export.read(folder)
        manifest["exported_at"] = "2026-01-01T00:00:00"
        (folder / "manifest.json").write_text(json.dumps(manifest))
        with self.assertRaises(export.ExportError):
            export.read(folder)

    def test_specs_not_in_an_export_are_untouched(self):
        self.trunk()
        self.load([("SRS", None, {"index.rst": SRS})])
        self.assertIsNotNone(models.find_by_id(self.conn, "SYS-1"))

    def test_a_baseline_cant_change(self):
        self.load([("SRS", "1.0", {"index.rst": SRS})])
        _, outcomes = self.load([("SRS", "1.0", {"index.rst": SRS})])
        self.assertEqual(outcomes, [("SRS@1.0", "unchanged")])
        with self.assertRaises(store.ImportError_):
            self.load([("SRS", "1.0", {"index.rst": SRS.replace("40%", "45%")})])

    def test_a_failed_import_changes_nothing(self):
        self.trunk()
        before = self.conn.execute("SELECT COUNT(*) FROM imports").fetchone()[0]
        with self.assertRaises(store.ImportError_):
            self.load([("SRS", None, {"index.rst": SRS.replace("40%", "45%")})],
                      sets=[("R1", {"SRS": "9.9"})])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM imports").fetchone()[0], before)
        self.assertIn("40%", models.find_by_id(self.conn, "SW-1").text)

    def test_an_id_moving_into_another_trunk_spec_is_refused(self):
        self.trunk()
        with self.assertRaises(store.ImportError_):
            self.load([("OTHER", None, {"index.rst": SYS})])

    def test_sets_pin_baselines(self):
        self.load([("SYS", "1", {"index.rst": SYS}), ("SRS", "1", {"index.rst": SRS})],
                  sets=[("R1", {"SYS": "1", "SRS": "1"})])
        self.assertEqual(sorted(models.resolve(self.conn, "set:R1")), ["SRS", "SYS"])
        with self.assertRaises(store.ImportError_):
            self.load([], sets=[("R1", {"SYS": "1"})])


class TestQueries(ExportCase):
    def setUp(self):
        super().setUp()
        self.load([("SYS", "1", {"index.rst": SYS}), ("SRS", "1", {"index.rst": SRS})],
                  sets=[("R1", {"SYS": "1", "SRS": "1"})])
        self.trunk()
        self.trunk(srs=SRS.replace("below 40%", "below 45%").split("Time\n")[0]
                   + "\n.. requirement:: SW-9\n   :satisfies: NOPE-1\n\n   New shall be.\n")

    def test_contexts(self):
        self.assertIn("45%", models.find_by_id(self.conn, "SW-1").text)
        self.assertIn("40%", models.find_by_id(self.conn, "SW-1", "set:R1").text)
        self.assertIn("40%", models.find_by_id(self.conn, "SW-1", "trunk@2").text)
        self.assertEqual(list(models.resolve(self.conn, "SRS@1")), ["SRS"])
        for bad in ("set:R9", "SRS@9", "trunk@x", "nonsense"):
            with self.assertRaises(models.ContextError):
                models.resolve(self.conn, bad)

    def test_requirements_carry_their_spec_and_attributes(self):
        sw1 = models.find_by_id(self.conn, "SW-1")
        self.assertEqual((sw1.spec, sw1.subsystem, sw1.satisfies), ("SRS", "EPS", ("SYS-1",)))
        self.assertEqual(sw1.attributes["verification"], "Test")
        self.assertEqual(models.subsystems(self.conn, "set:R1"), ["EPS", "TIM"])

    def test_diff_between_contexts(self):
        changes = {c.id: c.changes for c in models.diff(self.conn, "set:R1", "trunk")}
        self.assertEqual(changes, {"SW-1": ("text",), "SW-3": ("removed",),
                                   "SW-9": ("added",)})
        only = models.diff(self.conn, "set:R1", "trunk", subsystem="TIM")
        self.assertEqual([c.id for c in only], ["SW-3"])
        self.assertEqual(models.diff(self.conn, "set:R1", "trunk@2"), [])

    def test_history_of_a_requirement(self):
        events = [(e.kind, e.label, e.changes) for e in models.history(self.conn, "SW-1")]
        self.assertEqual(events, [("baseline", "SRS@1", ()), ("trunk", "SRS", ("added",)),
                                  ("trunk", "SRS", ("text",))])

    def test_trace_issues(self):
        self.assertEqual(models.trace_issues(self.conn), [("SW-9", "NOPE-1", "missing")])


class TestSampleHistory(unittest.TestCase):
    def test_the_sample_history_imports_through_the_cli(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        folders = demo.write_sample_exports(tmp / "exports")
        with redirect_stdout(StringIO()), self.assertRaises(SystemExit) as exit:
            cli.main(["requirements", "import", *map(str, folders),
                      "--dbpath", str(tmp / "db")])
        self.assertEqual(exit.exception.code, 0)
        conn = connect(tmp / "db")
        self.addCleanup(conn.close)
        changes = {c.id: c.changes for c in models.diff(conn, "set:Release 1", "trunk")}
        self.assertEqual(changes, {
            "SEG-SPC-007": ("text",), "VM-EPS-002": ("text",), "VM-EPS-007": ("added",),
            "VM-MEM-001": ("links",), "VM-TC-001": ("metadata",),
            "VM-TIM-005": ("section",), "VMCFUE00003": ("links",),
            "VMCREL00008": ("removed",)})
        self.assertEqual(models.trace_issues(conn),
                         [("VMCFUE00003", "SEG-AIR-099", "missing")])


if __name__ == "__main__":
    unittest.main()
