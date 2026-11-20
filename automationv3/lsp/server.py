"""The Language Server Protocol, as messages in and messages out

`Server.handle(message)` takes one JSON-RPC message (a dict) and gives
the messages to send back, in order: the response to a request, and any
notifications (the diagnostics a change brought). Nothing here reads or
writes a stream, so the same server sits behind stdin and stdout
(stdio.py) and behind the web app (web/editor.py).

Supported: initialize, shutdown, exit; documents opened, changed (the
whole text each time), saved and closed; diagnostics, published after
each of those for every open document and the files it loads;
completion (names in a block, the paths below a ref, requirement ids in
:req:), hover and signature help.

Documents are named by URI. A file: URI is a path, which must be under
the root; with any other scheme the URI's path is taken as relative to
the root (the web editor's "rvt:///GDN/tc_gdn_001.rst").
"""

from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlparse

from .service import BLOCK, FUNCTION, KEYWORD, PATH, REQUIREMENT, VARIABLE, Service
from ..framework.analysis import ERROR

SERVER_NOT_INITIALIZED, METHOD_NOT_FOUND, INTERNAL_ERROR = -32002, -32601, -32603
SEVERITY_ERROR, SEVERITY_WARNING = 1, 2
# CompletionItemKind
KINDS = {FUNCTION: 3, VARIABLE: 6, BLOCK: 7, KEYWORD: 14, REQUIREMENT: 18, PATH: 10}
# Blocks first where a call starts, then what scripts define
ORDER = {BLOCK: "1", REQUIREMENT: "1", PATH: "1", VARIABLE: "2", FUNCTION: "3", KEYWORD: "4"}


def utf16(text, col):
    """The UTF-16 offset of character `col` of `text` (what the protocol
    counts columns in)"""
    return len(text[:col].encode("utf-16-le")) // 2


def characters(text, units):
    """The character offset of UTF-16 offset `units` of `text`"""
    return len(text.encode("utf-16-le")[:units * 2].decode("utf-16-le", "ignore"))


class Server:
    def __init__(self, root=None, requirements=None):
        """`root`: the scripts root, when it is known before the client
        says (the web app's workspaces); else initialize gives it.
        `requirements(root)` gives what answers for requirements there
        (see Service), or None."""
        self.requirements = requirements or (lambda root: None)
        self.service = Service(root, self.requirements(root)) if root is not None else None
        self.initialized = False
        self.exited = False
        self.uris = {}  # path -> the URI the client knows it by
        self.scheme = "file"
        self.published = {}  # path -> the diagnostics last sent

    # Messages

    def handle(self, message):
        """The messages answering `message`"""
        method, id = message.get("method"), message.get("id")
        params = message.get("params") or {}
        if method is None:
            return []  # a response to something we never asked
        handler = getattr(self, "on_" + method.replace("/", "_").replace("$", "_"), None)
        if method != "initialize" and not self.initialized and method != "exit":
            return [self.error(id, SERVER_NOT_INITIALIZED, "not initialized")] if id is not None else []
        if handler is None:
            return [self.error(id, METHOD_NOT_FOUND, f"{method} isn't supported")] if id is not None else []
        try:
            result, more = handler(params)
        except Exception as e:
            if id is None:
                return []
            return [self.error(id, INTERNAL_ERROR, f"{type(e).__name__}: {e}")]
        answer = [{"jsonrpc": "2.0", "id": id, "result": result}] if id is not None else []
        return answer + more

    def error(self, id, code, message):
        return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}

    # Lifecycle

    def on_initialize(self, params):
        if self.service is None:
            folders = params.get("workspaceFolders") or []
            uri = (folders[0].get("uri") if folders else None) or params.get("rootUri")
            root = Path(unquote(urlparse(uri).path)) if uri else Path(params.get("rootPath") or ".")
            self.service = Service(root, self.requirements(root))
        self.initialized = True
        return {
            "capabilities": {
                "positionEncoding": "utf-16",
                "textDocumentSync": {"openClose": True, "change": 1, "save": {"includeText": False}},
                "completionProvider": {"triggerCharacters": ["(", "`", ".", '"']},
                "hoverProvider": True,
                "signatureHelpProvider": {"triggerCharacters": ["(", " "]},
            },
            "serverInfo": {"name": "automation-v3"},
        }, []

    def on_initialized(self, params):
        return None, []

    def on_shutdown(self, params):
        return None, []

    def on_exit(self, params):
        self.exited = True
        return None, []

    def on___cancelRequest(self, params):
        return None, []

    # Documents

    def path(self, uri):
        """The path, relative to the root, a URI names; None for a file
        outside the root"""
        parsed = urlparse(uri)
        path = unquote(parsed.path)
        if parsed.scheme == "file":
            try:
                found = str(PurePosixPath(Path(path).resolve().relative_to(self.service.root)))
            except ValueError:
                return None
        else:
            found = str(PurePosixPath(path.lstrip("/")))
            if found.startswith(".."):
                return None
        self.scheme = parsed.scheme
        self.uris[found] = uri
        return found

    def uri(self, path):
        if path in self.uris:
            return self.uris[path]
        if self.scheme == "file":
            return (self.service.root / path).as_uri()
        return f"{self.scheme}:///{quote(path)}"

    def on_textDocument_didOpen(self, params):
        document = params["textDocument"]
        path = self.path(document["uri"])
        if path is not None:
            self.service.texts[path] = document.get("text", "")
        return None, self.publish()

    def on_textDocument_didChange(self, params):
        path = self.path(params["textDocument"]["uri"])
        changes = params.get("contentChanges") or []
        if path is not None and changes:
            self.service.texts[path] = changes[-1]["text"]  # whole documents (change: 1)
        return None, self.publish()

    def on_textDocument_didSave(self, params):
        return None, self.publish()

    def on_textDocument_didClose(self, params):
        path = self.path(params["textDocument"]["uri"])
        self.service.texts.pop(path, None)
        self.service.resolved.pop(path, None)
        return None, self.publish()

    # Diagnostics

    def publish(self):
        """publishDiagnostics notifications for every file whose
        problems aren't what was last sent"""
        found = self.service.problems()
        messages = []
        for path in sorted(set(found) | set(self.published)):
            lines = (self.service.text(path) or "").splitlines()
            diagnostics = [self.diagnostic(p, lines) for p in found.get(path, [])]
            if diagnostics == self.published.get(path) or (not diagnostics and path not in self.published
                                                           and path not in self.service.texts):
                continue
            if path in found:
                self.published[path] = diagnostics
            else:
                self.published.pop(path, None)
            messages.append({"jsonrpc": "2.0", "method": "textDocument/publishDiagnostics",
                             "params": {"uri": self.uri(path), "diagnostics": diagnostics}})
        return messages

    def diagnostic(self, problem, lines):
        def position(line, col):
            text = lines[line] if 0 <= line < len(lines) else ""
            return {"line": max(line, 0), "character": utf16(text, col)}
        return {
            "range": {"start": position(problem.line, problem.col),
                      "end": position(problem.end_line, problem.end_col)},
            "severity": SEVERITY_ERROR if problem.severity == ERROR else SEVERITY_WARNING,
            "source": "automation-v3",
            "message": problem.message,
        }

    # Completion

    def on_textDocument_completion(self, params):
        path = self.path(params["textDocument"]["uri"])
        if path is None:
            return {"isIncomplete": False, "items": []}, []
        line, units = params["position"]["line"], params["position"]["character"]
        lines = (self.service.text(path) or "").splitlines()
        col = characters(lines[line], units) if line < len(lines) else 0
        items = []
        for item in self.service.complete(path, line, col):
            found = {"label": item.label, "kind": KINDS[item.kind],
                     "sortText": ORDER[item.kind] + item.label}
            if item.detail:
                found["detail"] = item.detail
            if item.doc:
                found["documentation"] = item.doc
            if item.start is not None:  # it replaces more than the name being typed: a whole path
                text = lines[line] if line < len(lines) else ""
                found["filterText"] = item.label
                found["textEdit"] = {"newText": item.label, "range": {
                    "start": {"line": line, "character": utf16(text, item.start)},
                    "end": {"line": line, "character": units}}}
            items.append(found)
        return {"isIncomplete": False, "items": items}, []

    # Hover and signature help

    def place(self, params):
        """(path, line, character column) of a request's position, or None"""
        path = self.path(params["textDocument"]["uri"])
        if path is None:
            return None
        line, units = params["position"]["line"], params["position"]["character"]
        lines = (self.service.text(path) or "").splitlines()
        text = lines[line] if line < len(lines) else ""
        return path, line, characters(text, units), text

    def on_textDocument_hover(self, params):
        place = self.place(params)
        found = self.service.hover(*place[:3]) if place else None
        if found is None:
            return None, []
        markdown, start, end = found
        line, text = place[1], place[3]
        return {"contents": {"kind": "markdown", "value": markdown},
                "range": {"start": {"line": line, "character": utf16(text, start)},
                          "end": {"line": line, "character": utf16(text, end)}}}, []

    def on_textDocument_signatureHelp(self, params):
        place = self.place(params)
        found = self.service.signatures(*place[:3]) if place else None
        if found is None:
            return None, []
        signatures, which, parameter = found
        return {"signatures": [{"label": s.label, "documentation": s.doc,
                                "parameters": [{"label": p} for p in s.parameters]}
                               for s in signatures],
                "activeSignature": which, "activeParameter": parameter}, []
