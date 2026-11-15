"""The language server: the service, the protocol, stdio and the web route"""

import io
import json
import shutil
import tempfile
import unittest
from contextlib import closing
from unittest import mock

from automationv3.framework import lisp, refs
from automationv3.framework.refs import Ref
from pathlib import Path

from automationv3.lsp import stdio
from automationv3.lsp.server import Server, characters, utf16
from automationv3.lsp.service import Service, local_names, scan
from automationv3.services.database import connect, init_db
from automationv3.web.app import create_app
from .data import make_workspaces as gitutil

CORE = """\
Core
====

.. rvt::

   (environments :sim)
   (uut :demo)
   (def limit 80)
   (defn double [x] (* 2 x))
"""

SCRIPT = """\
Brakes
======
Checks the brakes.

.. rvt::
   :definitions:

   (def target 60)

.. rvt::

   (Verify target <= limit)
   (Verify (double target) > limit)
"""


def request(id, method, **params):
    return {"jsonrpc": "2.0", "id": id, "method": method, "params": params}


def notify(method, **params):
    return {"jsonrpc": "2.0", "method": method, "params": params}


class Rooted(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        (self.root / "BRA").mkdir()
        (self.root / "core.rst").write_text(CORE)
        (self.root / "BRA" / "tc.rst").write_text(SCRIPT)


class TestService(Rooted):
    def setUp(self):
        super().setUp()
        self.service = Service(self.root)

    def problems(self, path="BRA/tc.rst"):
        return [(p.severity, p.message, p.line, p.col, p.end_col)
                for p in self.service.problems().get(path, [])]

    def test_a_clean_script_has_no_problems(self):
        self.service.texts["BRA/tc.rst"] = SCRIPT
        self.assertEqual(self.service.problems(), {"BRA/tc.rst": []})

    def test_an_unknown_name_is_where_it_is_written(self):
        self.service.texts["BRA/tc.rst"] = SCRIPT.replace("<= limit", "<= limt")
        (problem,) = self.problems()
        self.assertEqual(problem[0], "error")
        self.assertIn("unknown name limt", problem[1])
        self.assertEqual(problem[2:], (11, 21, 25))

    def test_unreadable_code_is_where_the_reader_stopped(self):
        self.service.texts["BRA/tc.rst"] = SCRIPT + "   (Verify (double"
        self.assertEqual(self.problems(), [("error", "Missing closing ')'", 13, 18, 19)])
        self.service.texts["BRA/tc.rst"] = SCRIPT.replace(".. rvt::\n   :definitions:", ".. rvt::\n   :nonsense:")
        (problem,) = self.problems()
        self.assertIn('unknown option: "nonsense"', problem[1])
        self.assertEqual(problem[2], 4)

    def test_an_open_core_stands_in_for_the_one_on_disk(self):
        self.service.texts["BRA/tc.rst"] = SCRIPT
        self.service.texts["core.rst"] = CORE.replace("(def limit 80)", "(def ceiling 80)")
        messages = [p[1] for p in self.problems()]
        self.assertTrue(messages and all("unknown name limit" in m for m in messages), messages)
        self.assertEqual(self.problems("core.rst"), [])

    def test_a_core_is_checked_as_one(self):
        self.service.texts["core.rst"] = CORE + "   (Verify 1 = 1)\n"
        (problem,) = self.problems("core.rst")
        self.assertIn("core.rst may only contain", problem[1])

    def test_other_files_have_no_problems(self):
        self.service.texts["notes.txt"] = "(("
        self.service.texts["README.rst"] = "Read me\n=======\n"
        self.assertEqual(self.service.problems(), {"notes.txt": [], "README.rst": []})

    def complete(self, text, line, col):
        self.service.texts["BRA/tc.rst"] = text
        self.service.problems()
        return {i.label: i for i in self.service.complete("BRA/tc.rst", line, col)}

    def test_completion_offers_what_a_block_can_use(self):
        found = self.complete(SCRIPT + "   (Verify ", 13, 11)
        for name in ("target", "limit", "double", "demo", "+"):
            self.assertIn(name, found)
        self.assertEqual(found["double"].detail, "[x] in core.rst")
        self.assertEqual(found["target"].detail, "def in here")
        self.assertEqual(found["demo"].detail, "UUT handle")
        self.assertNotIn("Verify", found)  # not where an argument goes

    def test_blocks_complete_where_a_call_starts(self):
        found = self.complete(SCRIPT + "   (", 13, 4)
        self.assertEqual(found["Verify"].detail, "(Verify actual predicate args...)")
        self.assertIn("defn", found)

    def test_nothing_completes_outside_code(self):
        self.assertEqual(self.complete(SCRIPT, 2, 5), {})  # prose
        self.assertEqual(self.complete(SCRIPT, 5, 6), {})  # a block's options
        self.assertEqual(self.complete(SCRIPT + '   (Verify "ta', 13, 14), {})
        self.assertEqual(self.complete(SCRIPT + "   ; ta", 13, 7), {})

    def test_local_names_complete(self):
        found = self.complete(SCRIPT + "   (defn f [speed] (let [gap 1] (+ ", 13, 35)
        self.assertEqual(found["speed"].detail, "bound here")
        self.assertIn("gap", found)

    def test_scanning(self):
        self.assertEqual(local_names(scan("(defn f ([a] 1) ([a & more] (g ")), ["a", "more"])
        self.assertEqual(local_names(scan("(let [x 1 y (g 2)] (h ")), ["x", "y"])
        self.assertEqual(local_names(scan("(fn [a] a) (b ")), [])


REFS = """\
Refs
====
See :req:`R-1` and :req:`R-9`.

.. rvt::
   :definitions:

   (def cpu1 (sys/connector "sys.cpu1"))
   (def cpu2 (sys/connector "sys.cpu2"))
   (def nav cpu1.app.nav)
   (def cpus (group cpu1 cpu2))
   (def minimum 10)
   (def low minimum)
   (def twice (double minimum))
   (defn within? ([v lo hi] (and (>= v lo) (<= v hi))) ([v & more] true))

.. rvt::

   (Verify nav.time within? low 20)
   (Verify cpus.app.mode = :run)
"""


class Listed:
    """Requirements, as the service asks for them"""

    def __init__(self, *found):
        self.found = found

    def all(self):
        return list(self.found)

    def find(self, id):
        return next((r for r in self.found if r.id == id), None)


class Connector(Ref):
    """A kind of ref that can't say what is below a path"""


class TestWhatNamesAre(Rooted):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(lisp.global_env, {"sys/connector": refs.constructs(Connector)(
            lambda path: Connector(path))})
        patcher.start()
        self.addCleanup(patcher.stop)
        from automationv3.framework.requirement import Requirement
        self.service = Service(self.root, Listed(Requirement("R-1", "The brakes shall *hold*.", spec="SRS")))
        self.service.texts["BRA/tc.rst"] = REFS
        self.lines = REFS.splitlines()

    def hover(self, needle, line=None, inside=1):
        line = line if line is not None else max(n for n, l in enumerate(self.lines) if needle in l)
        found = self.service.hover("BRA/tc.rst", line, self.lines[line].index(needle) + inside)
        return found[0] if found else None

    def test_literals_and_aliases(self):
        self.assertIn("`low` is `10`.", self.hover("low"))
        self.assertNotIn(" is ", self.hover("minimum", 11))  # the code says it already
        self.assertNotIn(" is ", self.hover("twice", 13))  # only a run can tell

    def test_refs_and_their_paths(self):
        self.assertEqual(self.hover("nav.time"), "`nav.time` is a Connector ref `sys.cpu1.app.nav.time`.")
        self.assertIn("`nav` is a Connector ref `sys.cpu1.app.nav`.", self.hover("nav ", 9))
        self.assertEqual(self.hover("cpus.app.mode"),
                         "`cpus.app.mode` is a group of cpu1: Connector ref `sys.cpu1.app.mode`, "
                         "cpu2: Connector ref `sys.cpu2.app.mode`.")

    def test_definitions_blocks_and_builtins(self):
        self.assertIn("(defn within?", self.hover("within?"))
        self.assertIn("Defined in this script.", self.hover("within?"))
        self.assertIn("(defn double [x] (* 2 x))", self.hover("double", 13))
        self.assertIn("Defined in core.rst.", self.hover("double", 13))
        self.assertIn("(Verify actual predicate args...)", self.hover("Verify"))
        self.assertIn("builtin function", self.hover(">=", 14))
        self.assertIn("a parameter", self.hover("lo ", 14))
        self.assertIsNone(self.hover(":run"))
        self.assertIsNone(self.hover("Refs", 0))

    def test_handles_and_variation_values(self):
        text = REFS + "   (variations \"speed\" [\"slow\" [1] \"fast\" [9]])\n   (Verify speed > 0)\n   (.mode demo)\n"
        self.service.texts["BRA/tc.rst"] = text
        self.lines = text.splitlines()
        self.service.problems()
        self.assertIn("- slow: `1`\n- fast: `9`", self.hover("speed >"))
        self.assertIn("handle of the UUT", self.hover("demo)"))

    def test_requirements(self):
        self.assertEqual(self.hover("R-1"), "**R-1** (SRS)\n\nThe brakes shall *hold*.")
        self.assertIn("isn't a requirement", self.hover("R-9"))
        (problem,) = self.service.problems()["BRA/tc.rst"]
        self.assertEqual((problem.severity, problem.line, problem.col, problem.end_col), ("warning", 2, 25, 28))
        self.assertIn("R-9 isn't a requirement", problem.message)
        (item,) = self.service.complete("BRA/tc.rst", 2, 12)
        self.assertEqual((item.label, item.detail), ("R-1", "The brakes shall *hold*."))

    def test_requirements_are_not_checked_when_there_are_none(self):
        self.service.requirements = Listed()
        self.assertEqual(self.service.problems()["BRA/tc.rst"], [])
        self.service.requirements = None
        self.assertEqual(self.service.problems()["BRA/tc.rst"], [])
        self.assertIsNone(self.hover("R-1"))

    def signatures(self, line, before):
        found = self.service.signatures("BRA/tc.rst", line, len(before))
        return ([s.label for s in found[0]], found[1], found[2]) if found else None

    def test_signatures(self):
        self.assertEqual(self.signatures(18, "   (Verify nav.time within? "),
                         (["(Verify actual predicate args...)", "(Verify value)"], 0, 2))
        self.assertEqual(self.signatures(18, "   (Verify nav.time within? low 20"), 
                         (["(Verify actual predicate args...)", "(Verify value)"], 0, 2))
        self.service.texts["BRA/tc.rst"] = REFS + "   (within? 1 2 3 4"
        self.assertEqual(self.signatures(20, "   (within? 1 "), (["(within? v lo hi)", "(within? v more...)"], 0, 1))
        self.assertEqual(self.signatures(20, "   (within? 1 2 3 "), (["(within? v lo hi)", "(within? v more...)"], 1, 1))
        self.assertIsNone(self.signatures(2, "See "))


PATHS = """\
Paths
=====

.. rvt::
   :definitions:

   (def vm (connector "vm"))
   (def eps vm.eps)
   (def bad (connector "vm.epz"))
   (def lines (group eps.line.bus-computer eps.line.receivers))

.. rvt::

   (Verify eps.soc > 0)
   (Verify eps.sco > 0)
   (Verify lines.on = true)
   (Verify lines.of = true)
   (defn f [eps] eps.whatever)
   (Verify bad.soc > 0)
"""


class TestRefPaths(Rooted):
    """With the Vehicle Manager's connectors, whose kind of ref says
    what is below a path"""

    def setUp(self):
        super().setUp()
        self.service = Service(self.root)
        self.service.texts["BRA/tc.rst"] = PATHS
        self.lines = PATHS.splitlines()

    def test_the_hook(self):
        from automationv3.framework.refs import Ref
        from automationv3.plugins.vm.blocks import Connector
        self.assertIsNone(Ref.children("a.b"))
        self.assertEqual([c.name for c in Connector.children("")], ["vm"])
        soc = next(c for c in Connector.children("vm.eps") if c.name == "soc")
        self.assertEqual((soc.leaf, soc.detail), (True, "read-only"))
        self.assertEqual(Connector.children("vm.nope"), [])

    def test_paths_that_dont_exist(self):
        found = [(p.line, p.col, p.end_col, p.message.split(";")[0])
                 for p in self.service.problems()["BRA/tc.rst"]]
        self.assertEqual(found, [
            (8, 12, 32, "no epz below Connector vm (there: obc, mode, eps, tc, fdir, bench)"),
            (14, 11, 18, "no sco below Connector vm.eps (there: soc, charge-current, "
                         "max-charge-current, shed, line)"),
            (16, 11, 19, "eps.line.bus-computer: no of below Connector vm.eps.line.bus-computer "
                         "(there: on, tripped, switch-ms)"),
        ])  # not eps.whatever (eps is a parameter there), nor bad.soc (bad is reported where it's made)
        self.assertTrue(all(p.severity == "warning" for p in self.service.problems()["BRA/tc.rst"]))

    def complete(self, line, before):
        return [(i.label, i.detail, i.start) for i in self.service.complete("BRA/tc.rst", line, len(before))]

    def test_completing_paths(self):
        self.assertEqual(self.complete(13, "   (Verify eps.s")[:2],
                         [("eps.soc", "read-only", 11), ("eps.charge-current", "read-only", 11)])
        self.assertEqual(self.complete(15, "   (Verify lines.")[0], ("lines.on", "settable", 11))
        self.assertNotIn("eps.whatever", [l for l, _, _ in self.complete(17, "   (defn f [eps] eps.")])
        self.service.texts["BRA/tc.rst"] = PATHS + '   (def x (connector "vm.e'
        self.assertEqual(self.complete(19, '   (def x (connector "vm.e')[2], ("vm.eps", "28 connectors below", 22))

    def test_hovering_paths(self):
        hover = self.service.hover("BRA/tc.rst", 13, 14)[0]
        self.assertEqual(hover, "`eps.soc` is a Connector ref `vm.eps.soc`.\n\nread-only.")
        self.assertIn("no sco below Connector vm.eps", self.service.hover("BRA/tc.rst", 14, 14)[0])
        self.assertIn("- eps.line.receivers: settable.", self.service.hover("BRA/tc.rst", 15, 14)[0])

    def test_paths_complete_over_the_protocol(self):
        server = Server(self.root)
        server.handle(request(1, "initialize"))
        uri = (self.root / "BRA" / "tc.rst").as_uri()
        server.handle(notify("textDocument/didOpen", textDocument={"uri": uri, "text": PATHS}))
        (answer,) = server.handle(request(2, "textDocument/completion", textDocument={"uri": uri},
                                          position={"line": 13, "character": 16}))
        soc = next(i for i in answer["result"]["items"] if i["label"] == "eps.soc")
        self.assertEqual(soc["textEdit"], {"newText": "eps.soc", "range": {
            "start": {"line": 13, "character": 11}, "end": {"line": 13, "character": 16}}})
        self.assertEqual(soc["kind"], 10)


class TestServer(Rooted):
    def setUp(self):
        super().setUp()
        self.server = Server()
        self.uri = (self.root / "BRA" / "tc.rst").as_uri()
        (answer,) = self.server.handle(request(1, "initialize", rootUri=self.root.as_uri()))
        self.capabilities = answer["result"]["capabilities"]

    def open(self, text, uri=None):
        return self.server.handle(notify("textDocument/didOpen",
                                         textDocument={"uri": uri or self.uri, "text": text}))

    def test_capabilities(self):
        self.assertEqual(self.capabilities["textDocumentSync"]["change"], 1)
        self.assertIn("completionProvider", self.capabilities)

    def test_nothing_before_initialize(self):
        (answer,) = Server().handle(request(1, "textDocument/completion"))
        self.assertEqual(answer["error"]["code"], -32002)
        self.assertEqual(Server().handle(notify("textDocument/didOpen")), [])

    def test_opening_publishes_diagnostics(self):
        (published,) = self.open(SCRIPT.replace("<= limit", "<= limt"))
        self.assertEqual(published["method"], "textDocument/publishDiagnostics")
        self.assertEqual(published["params"]["uri"], self.uri)
        (diagnostic,) = published["params"]["diagnostics"]
        self.assertEqual(diagnostic["severity"], 1)
        self.assertEqual(diagnostic["range"], {"start": {"line": 11, "character": 21},
                                               "end": {"line": 11, "character": 25}})

    def test_diagnostics_are_sent_when_they_change(self):
        (published,) = self.open(SCRIPT)
        self.assertEqual(published["params"]["diagnostics"], [])

        def change(text):
            return self.server.handle(notify("textDocument/didChange", textDocument={"uri": self.uri},
                                             contentChanges=[{"text": text}]))
        self.assertEqual(change(SCRIPT + "\n"), [])  # still nothing wrong
        (published,) = change(SCRIPT.replace("<= limit", "<= limt"))
        self.assertEqual(len(published["params"]["diagnostics"]), 1)
        (published,) = change(SCRIPT)
        self.assertEqual(published["params"]["diagnostics"], [])
        self.assertEqual(self.server.handle(notify("textDocument/didClose", textDocument={"uri": self.uri})), [])

    def test_a_core_change_reaches_the_scripts_open_beside_it(self):
        self.open(SCRIPT)
        published = self.open(CORE.replace("(def limit 80)", ""), (self.root / "core.rst").as_uri())
        by_uri = {m["params"]["uri"]: m["params"]["diagnostics"] for m in published}
        self.assertTrue(by_uri[self.uri])
        self.assertEqual(by_uri[(self.root / "core.rst").as_uri()], [])

    def test_completion(self):
        self.open(SCRIPT + "   (Ver")
        (answer,) = self.server.handle(request(2, "textDocument/completion", textDocument={"uri": self.uri},
                                               position={"line": 13, "character": 7}))
        items = {i["label"]: i for i in answer["result"]["items"]}
        self.assertEqual(items["Verify"]["kind"], 7)
        self.assertTrue(items["Verify"]["sortText"] < items["double"]["sortText"])

    def test_hover_and_signature_help(self):
        self.open(SCRIPT)
        (answer,) = self.server.handle(request(2, "textDocument/hover", textDocument={"uri": self.uri},
                                               position={"line": 12, "character": 13}))
        self.assertIn("(defn double [x] (* 2 x))", answer["result"]["contents"]["value"])
        self.assertEqual(answer["result"]["range"], {"start": {"line": 12, "character": 12},
                                                     "end": {"line": 12, "character": 18}})
        (nothing,) = self.server.handle(request(3, "textDocument/hover", textDocument={"uri": self.uri},
                                                position={"line": 2, "character": 3}))
        self.assertIsNone(nothing["result"])
        (answer,) = self.server.handle(request(4, "textDocument/signatureHelp", textDocument={"uri": self.uri},
                                               position={"line": 12, "character": 19}))
        self.assertEqual(answer["result"]["signatures"][0]["label"], "(double x)")
        self.assertEqual(answer["result"]["activeParameter"], 0)

    def test_columns_are_utf16(self):
        self.assertEqual(utf16("a😀b", 2), 3)
        self.assertEqual(characters("a😀b", 3), 2)
        (published,) = self.open(SCRIPT.replace("(Verify target <= limit)", '(Verify "😀" = limt)'))
        (diagnostic,) = published["params"]["diagnostics"]
        self.assertEqual(diagnostic["range"]["start"]["character"], 18)  # 17 characters in

    def test_unknown_methods(self):
        (answer,) = self.server.handle(request(3, "textDocument/definition"))
        self.assertEqual(answer["error"]["code"], -32601)
        self.assertEqual(self.server.handle(notify("workspace/didChangeConfiguration")), [])

    def test_files_outside_the_root_are_left_alone(self):
        self.assertEqual(self.open("((", "file:///somewhere/else.rst"), [])

    def test_the_rvts_folder_of_the_root_is_the_scripts_root(self):
        (self.root / "rvts").mkdir()
        server = Server()
        server.handle(request(1, "initialize", rootUri=self.root.as_uri()))
        self.assertEqual(server.service.root, (self.root / "rvts").resolve())

    def test_other_schemes_name_paths_under_the_root(self):
        server = Server(self.root)
        server.handle(request(1, "initialize"))
        (published,) = server.handle(notify("textDocument/didOpen", textDocument={
            "uri": "rvt:///BRA/tc.rst", "text": SCRIPT.replace("<= limit", "<= limt")}))
        self.assertEqual(published["params"]["uri"], "rvt:///BRA/tc.rst")
        self.assertEqual(len(published["params"]["diagnostics"]), 1)


class TestStdio(Rooted):
    def test_a_session(self):
        def framed(message):
            body = json.dumps(message).encode()
            return b"Content-Length: %d\r\n\r\n" % len(body) + body
        uri = (self.root / "BRA" / "tc.rst").as_uri()
        sent = b"".join(map(framed, [
            request(1, "initialize", rootUri=self.root.as_uri()), notify("initialized"),
            notify("textDocument/didOpen", textDocument={"uri": uri, "text": SCRIPT + "   (Verify"}),
            request(2, "shutdown"), notify("exit")]))
        out = io.BytesIO()
        self.assertEqual(stdio.serve(stdin=io.BytesIO(sent), stdout=out), 0)
        out.seek(0)
        got = []
        while (message := stdio.read_message(out)) is not None:
            got.append(message)
        self.assertEqual([m.get("id", m.get("method")) for m in got],
                         [1, "textDocument/publishDiagnostics", 2])
        self.assertEqual(got[1]["params"]["diagnostics"][0]["message"], "Missing closing ')'")

    def test_hanging_up_without_shutdown_is_an_error(self):
        self.assertEqual(stdio.serve(stdin=io.BytesIO(b""), stdout=io.BytesIO()), 1)


class TestWebRoute(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        rvts = self.tmp / "master" / "rvts"
        (rvts / "BRA").mkdir(parents=True)
        (rvts / "core.rst").write_text(CORE)
        (rvts / "BRA" / "tc.rst").write_text(SCRIPT)
        gitutil.create_repo(self.tmp / "master")
        with closing(connect(self.tmp / "a.db")) as conn:
            init_db(conn)
        app = create_app(DB_PATH=str(self.tmp / "a.db"), WORKSPACE_PATH=self.tmp / "master",
                         REPORTS_PATH=str(self.tmp / "reports"))
        app.testing = True
        self.client = app.test_client()

    def send(self, session, *messages):
        response = self.client.post("/workspace/master/lsp", json={"session": session, "messages": list(messages)})
        self.assertEqual(response.status_code, 200, response.get_data(True))
        return response.json["messages"]

    def test_a_page_talks_to_its_own_server(self):
        opened = notify("textDocument/didOpen", textDocument={
            "uri": "rvt:///BRA/tc.rst", "text": SCRIPT.replace("<= limit", "<= limt")})
        answer, published = self.send("page-one", request(1, "initialize"), opened)
        self.assertEqual(answer["id"], 1)
        self.assertEqual(len(published["params"]["diagnostics"]), 1)
        (completion,) = self.send("page-one", request(2, "textDocument/completion",
                                                      textDocument={"uri": "rvt:///BRA/tc.rst"},
                                                      position={"line": 11, "character": 11}))
        self.assertIn("target", [i["label"] for i in completion["result"]["items"]])
        # another page has opened nothing
        (other,) = self.send("page-two", request(1, "initialize"))
        self.assertEqual(other["id"], 1)
        self.assertEqual(self.send("page-two", notify("textDocument/didSave", textDocument={"uri": "rvt:///x"})), [])

    def test_a_session_is_needed(self):
        self.assertEqual(self.client.post("/workspace/master/lsp", json={"messages": []}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
