"""The workspace editor: a file as cards (framework/cards.py), saved to
the worktree on disk

The workspace page shows an editable file as its cards. The page keeps
the cards it shows, edited or not, and sends them all back to save: a
card that wasn't edited comes back with the source it was cut from, so
the file is rebuilt with only the edited cards rewritten.

A save names the hash of the file the cards were cut from. If the file
on disk is another by then (a checkout, another editor), the save is
refused (409) unless it is forced.

Editing is for workspaces whose files are worktrees on this machine
(`workspaces().editable`): the central server shows what was pushed.
"""

import dataclasses
import difflib
import hashlib
import json
import os
import re
import tempfile
import threading
import time
from html import escape
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from docutils import nodes
from flask import abort, current_app, jsonify, request

from ..framework import cards as card_model
from ..framework import source
from ..framework.cards import Card, PROSE, RVT, SOURCE, VARIANT
from ..services.workspace import (create_folder, delete_file, move_file,
                                  valid_entry_name, write_file)
from . import documents
from .context import workspaces
from .db import get_db

FIELDS = ("kind", "source", "index", "text", "title", "definitions", "table",
          "variations", "code")
KINDS = (PROSE, RVT, SOURCE, VARIANT)
DEEPEST = 12  # variants inside variants
MAX_TABS = 40


def script_version():
    """A number that changes when the editor's scripts do, for their
    addresses: a browser must not pair an old script with a new server"""
    folder = Path(current_app.static_folder) / "js"
    return max(int((folder / name).stat().st_mtime)
               for name in ("editor.js", "codemirror.bundle.js"))


def editable():
    """Files are edited where they are worktrees on this machine, and
    never on the central server"""
    from . import auth
    return bool(getattr(workspaces(), "editable", True)) and not auth.accounts_enabled()


def read(path):
    """The file's text exactly as it is on disk (line ends kept)"""
    return path.read_bytes().decode("utf-8")


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]


def disk_hash(path):
    """The hash of the file at `path`, or None if there is none"""
    try:
        return text_hash(read(path))
    except (OSError, UnicodeDecodeError):
        return None


def file_cards(path, text):
    """The cards of a file's text: an rst file's sections and blocks, any
    other text file as one card of source"""
    if path.suffix == ".rst":
        return card_model.split(text)
    if not text:
        return []
    return [Card(SOURCE, text, 1, 0, text=card_model.without_tail(text))]


# A card on the page


def heading_lines(text):
    """How many lines of a prose card's text are its heading: through
    the underline of its first title (2, or 3 with an overline)"""
    tree = source.parse(text.lstrip("\n"))
    title = next(tree.findall(nodes.title), None)
    span = source.locate(tree, title) if title is not None else None
    return span.line + 1 if span is not None else 0


def failed(text, error):
    return (f'<div class="ed-unreadable">{escape(str(error))}</div>'
            f'<pre class="ui-pre">{escape(text)}</pre>')


def variant_head(variations):
    """A variant card's own view: which variations it is for (its
    children show below it)"""
    names = " ".join(f"<code>{escape(name)}</code>" for name in variations) \
        or '<span class="ed-unreadable">no variations: say which</span>'
    return f'<p class="ed-variant__head"><span class="ed-variant__label">Only for</span> {names}</p>'


def card_html(card, diagnostics=(), plain=False):
    """A card as the page shows it when it isn't being edited. An rvt
    card shows as its steps do on a script's page, with the `diagnostics`
    (see workspace.diagnostic_views) about its lines."""
    if card.kind == VARIANT:
        return variant_head(card.variations)
    text = card_model.written(card) if card.source is None else card.source
    if plain:
        return f'<pre class="ui-pre">{escape(text)}</pre>'
    try:
        if card.kind == PROSE:
            body, heading = card.text, ""
            if card.source is None:  # an edited card: does it start with a heading?
                found = card_model.split(card.text)
                first = found[0] if found else card
                card = dataclasses.replace(
                    card, heading=first.heading,
                    level=(card.level or 2) if first.heading else 0)
            if card.heading:
                level = min(max(card.level, 1), 6)
                heading = f'<h{level} class="ed-heading">{escape(card.heading)}</h{level}>'
                body = "\n".join(card.text.lstrip("\n").splitlines()[heading_lines(card.text):])
            return heading + (documents.rst_document(body) if body.strip() else "")
        own = []
        if card.source is not None and card.line:
            last = card.line + len(text.splitlines()) - 1
            for d in diagnostics:
                if d.get("line") is not None and card.line <= d["line"] <= last:
                    d["inline"] = True  # shown here, so listed briefly above
                    own.append({**d, "line": d["line"] - card.line + 1})
        return documents.script_document(text, diagnostics=own)
    except Exception as e:  # unreadable: show it as it is written
        return failed(text, e)


def payload(card):
    """What the page keeps of a card, and sends back to save and to the
    language server (a variant's children each keep their own)"""
    data = {name: getattr(card, name) for name in FIELDS}
    data["level"] = card.level
    if card.kind == VARIANT:
        data["count"] = card.count
    return data


def views(found, plain=False, diagnostics=()):
    """[{kind, html, data, children}] for cards, a variant's children
    with it"""
    return [{"kind": card.kind, "html": card_html(card, diagnostics, plain),
             "data": payload(card),
             "children": views(card.children, plain, diagnostics)}
            for card in found]


def drafted(path, relative, text):
    """A file that isn't on disk yet, for the page to open as a tab with
    unsaved edits: its path, and its cards with their HTML"""
    plain = path.suffix != ".rst"
    found = file_cards(path, text)
    documents.ready()
    return {"path": str(relative), "count": len(found), "cards": views(found, plain)}


def card_views(path, text, diagnostics=()):
    """views() of the cards of a file's text, each card's data as JSON"""
    def as_json(found):
        return [{**view, "data": json.dumps(view["data"]), "children": as_json(view["children"])}
                for view in found]
    return as_json(views(file_cards(path, text), path.suffix != ".rst", diagnostics))


def locate(path, text, line, col=0):
    """Where file line `line` (1-based) and column `col` of a file's text
    are among its cards, as the page counts them: {card (its place in
    walk order), line, character (in what the card's editor holds)}; None
    past the cards. The innermost card wins, as for the language server's
    positions (PageSession.card_at)."""
    found = file_cards(path, text)
    _, places = card_model.placed(found, len(found))
    at, best = line - 1, None
    for index, place in enumerate(places):
        if place is not None and place.start <= at < place.end:
            best = (index, place)
    if best is None:
        return None
    index, place = best
    return {"card": index, "line": max(at - place.code_start, 0),
            "character": max(col - place.code_indent, 0)}


def as_card(data, depth=0):
    """The Card of what the page sent, or abort(400)"""
    if not isinstance(data, dict) or data.get("kind") not in KINDS or depth > DEEPEST:
        abort(400)
    source, index = data.get("source"), data.get("index")
    variations = data.get("variations") or []
    if isinstance(variations, str):
        variations = variations.split(",")
    children, count = data.get("children") or [], data.get("count") or 0
    try:
        ok = ((source is None or isinstance(source, str))
              and (index is None or isinstance(index, int))
              and all(isinstance(v, str) for v in variations)
              and isinstance(children, list) and isinstance(count, int))
    except TypeError:
        ok = False
    if not ok:
        abort(400)
    return Card(data["kind"], source, index=index if source is not None else None,
                children=[as_card(c, depth + 1) for c in children], count=count,
                text=str(data.get("text") or ""), title=str(data.get("title") or "") or None,
                level=int(data.get("level") or 0),
                definitions=bool(data.get("definitions")), table=bool(data.get("table")),
                variations=[v.strip() for v in variations if v.strip()],
                code=str(data.get("code") or ""))


def sent_text(body):
    """The file text of the cards a request sent"""
    sent = body.get("cards")
    if not isinstance(sent, list):
        abort(400)
    count = body.get("count")
    return card_model.build([as_card(c) for c in sent],
                            count if isinstance(count, int) else None)


def write(path, text):
    """Replace the file at `path` with `text`, all or nothing"""
    write_file(path, text)


# New files


def file_name(title):
    """A file name for a script titled `title`"""
    name = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return f"{name or 'script'}.rst"


def titled(title, char="=", over=True):
    line = char * max(len(title), 3)
    return f"{line}\n{title}\n{line}" if over else f"{title}\n{line}"


def skeleton(title, requirement=None, intro=None):
    """The text of a new script: its title, a Requirements section and
    a first block of steps still to be written"""
    lines = [titled(title)]
    if intro:
        lines += [intro]
    lines += ["", "Requirements", "------------"]
    if requirement:
        lines += [f"1. :req:`{requirement}`"]
    lines += ["", "Steps", "-----", "", ".. rvt::", "", "   (TBD)", ""]
    return "\n".join(lines)


def retitled(text, title):
    """`text` with its document title (its first heading) replaced"""
    found = card_model.split(text)
    first = next((c for c in found if c.heading), None)
    if first is None:
        return titled(title) + "\n\n" + text
    lines = first.text.lstrip("\n").splitlines()
    size = heading_lines(first.text)
    new = "\n".join([titled(title, lines[size - 1][0], over=size == 3)] + lines[size:])
    first.source = new + first.source[len(first.text):]
    return "".join(c.source for c in found)


def folders(root):
    """Every folder under `root`, as paths relative to it ("" is the root)"""
    found = [""]
    for folder, names, _ in os.walk(root):
        names[:] = sorted(n for n in names if not n.startswith("."))
        found += [(Path(folder) / n).relative_to(root).as_posix() for n in names]
    return sorted(found)


def expand_to(conn, workspace_id, relative, itself=False):
    """Open the tree down to `relative` (and the folder `itself`)"""
    from ..services.database import expand_nodes
    parts = PurePosixPath(relative).parts
    parts = parts if itself else parts[:-1]
    expand_nodes(conn, workspace_id,
                 [str(PurePosixPath(*parts[:n])) for n in range(1, len(parts) + 1)])


# Open tabs, per workspace


def open_tabs(conn, workspace_id):
    """([path], the active path or None), in tab order"""
    from ..services.database import open_tabs as _open_tabs
    return _open_tabs(conn, workspace_id)


def set_open_tabs(conn, workspace_id, paths, active):
    from ..services.database import set_open_tabs as _set_open_tabs
    _set_open_tabs(conn, workspace_id, paths, active, max_tabs=MAX_TABS)


# The language server's sessions: one per page showing a workspace

LSP_IDLE = 2 * 3600  # seconds a session is kept after its last message
LSP_SESSIONS = 40
_lsp_lock = threading.Lock()


class PageRequirements:
    """The requirements the language server answers from, for the
    request being handled: those of the context its workspace verifies.
    The local client asks the central server for one at a time, and
    can't list them."""

    def __init__(self):
        self.key, self.listed = None, []

    def find(self, id):
        from .app import requirement_lookup
        return requirement_lookup(id)

    def all(self):
        from flask import g
        from ..services.requirements import models
        from .app import requirement_key
        if current_app.config.get("REMOTE_REQUIREMENTS") is not None:
            return []
        key = requirement_key()
        if key != self.key:
            self.key = key
            self.listed = models.find_all(get_db(), context=g.get("requirement_context"))
        return self.listed


class PageSession:
    """A page's language server (lsp/server.py), spoken to in cards.

    The page sends a file as its cards; the text the server checks is
    built from them here (cards.placed), as a save would build it, and
    each position goes between the two: the server's are lines and
    UTF-16 columns of the file, the page's a card (its place in walk
    order of the cards it sent) and a line and column of what that
    card's editor holds."""

    def __init__(self, root):
        from ..lsp.server import Server
        self.changed = set()  # paths whose problems or cards changed
        self.started = False  # the page has said it starts (a page this is new to must start over)
        self.server = Server(root, lambda root: PageRequirements())
        self.server.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})
        self.server.handle({"jsonrpc": "2.0", "method": "initialized", "params": {}})
        self.places = {}  # path -> [(Place or None, top level?)], in walk order
        self.diagnostics = {}  # path -> the server's diagnostics last published
        self.lock = threading.Lock()
        self.used = time.monotonic()
        self.next = 1

    @staticmethod
    def uri(path):
        return "rvt:///" + quote(path)

    def handle(self, message):
        """Hand the server one message; keep what it publishes"""
        from urllib.parse import unquote
        answers = self.server.handle(message)
        for answer in answers:
            if answer.get("method") == "textDocument/publishDiagnostics":
                path = unquote(answer["params"]["uri"].removeprefix("rvt:///"))
                self.diagnostics[path] = answer["params"]["diagnostics"]
                self.changed.add(path)
        return answers

    def sync(self, path, sent, count):
        """The file at `path` is now what cards `sent` build"""
        text, places = card_model.placed(sent, count)
        top = {id(card) for card in sent}
        self.places[path] = [(place, id(card) in top)
                             for card, place in zip(card_model.walk(sent), places)]
        method = "textDocument/didChange" if self.server.is_open(self.uri(path)) else "textDocument/didOpen"
        params = ({"textDocument": {"uri": self.uri(path)}, "contentChanges": [{"text": text}]}
                  if method.endswith("didChange")
                  else {"textDocument": {"uri": self.uri(path), "languageId": "rst", "text": text}})
        self.handle({"jsonrpc": "2.0", "method": method, "params": params})
        self.changed.add(path)

    def close(self, path):
        self.places.pop(path, None)
        self.handle({"jsonrpc": "2.0", "method": "textDocument/didClose",
                     "params": {"textDocument": {"uri": self.uri(path)}}})

    def card_at(self, path, line):
        """The index of the innermost card a file line is in; past the
        end, the last top-level card's"""
        found = None
        for index, (place, _) in enumerate(self.places.get(path, [])):
            if place is not None and place.start <= line < place.end:
                found = index
        if found is None:
            tops = [i for i, (place, top) in enumerate(self.places.get(path, []))
                    if top and place is not None]
            found = tops[-1] if tops else None
        return found

    def problem(self, path, d):
        """A diagnostic as the page draws it: its card and where in it,
        and its line in the file (for the Problems panel)"""
        start, end = d["range"]["start"], d["range"]["end"]
        found = {"line": start["line"], "severity": d["severity"], "message": d["message"],
                 "card": None}
        index = self.card_at(path, start["line"])
        if index is not None:
            place = self.places[path][index][0]
            found.update(card=index, **{
                key: {"line": at["line"] - place.code_start,
                      "character": at["character"] - place.code_indent}
                for key, at in (("from", start), ("to", end))})
        return found

    def problems(self):
        """{path: problems} for each file whose problems, or whose cards,
        changed since this was last asked"""
        found = {path: [self.problem(path, d) for d in self.diagnostics.get(path, [])]
                 for path in sorted(self.changed)}
        self.changed = set()
        return found

    def request(self, data):
        """The answer to a hover, completion or signature request, which
        names a path, a card and a line and column in it; None when the
        page's cards for that path aren't known (it must send them)"""
        methods = {"hover": "textDocument/hover", "completion": "textDocument/completion",
                   "signature": "textDocument/signatureHelp"}
        path, index = data.get("path"), data.get("card")
        method = methods.get(data.get("method"))
        if isinstance(data.get("code"), str):
            if method is None or not isinstance(path, str) or not isinstance(data.get("line"), int) \
                    or not isinstance(data.get("character"), int):
                abort(400)
            return self.prompt_request(method, path, data["code"], data["line"],
                                       data["character"]), False
        places = self.places.get(path)
        if method is None or not isinstance(index, int) or not isinstance(data.get("line"), int) \
                or not isinstance(data.get("character"), int):
            abort(400)
        if places is None:
            return None, True
        if not 0 <= index < len(places) or places[index][0] is None:
            return {"result": None}, False
        place = places[index][0]
        self.next += 1
        answers = self.handle({"jsonrpc": "2.0", "id": self.next, "method": method, "params": {
            "textDocument": {"uri": self.uri(path)},
            "position": {"line": place.code_start + data["line"],
                         "character": place.code_indent + data["character"]}}})
        result = next((a.get("result") for a in answers if a.get("id") == self.next), None)
        if result and method == "textDocument/hover" and result.get("range"):
            result["range"] = {key: {"line": at["line"] - place.code_start,
                                     "character": at["character"] - place.code_indent}
                               for key, at in result["range"].items()}
        if result and method == "textDocument/completion":
            for item in result.get("items", []):
                item.pop("textEdit", None)  # the page replaces the word it completes
        return {"result": result}, False

    def prompt_request(self, method, path, code, line, character):
        """A request about the console's prompt (`code`, at `line` and
        `character` of it), asked as if it were a block at the end of
        `path`, the console's script, so it sees what the script's blocks
        see. The script stays as the server had it."""
        service = self.server.service
        had = path in service.texts
        before = service.text(path) or ""
        if path not in service.resolved and before:  # what it loads and declares: check it once
            service.texts[path] = before
            try:
                service.check(path)
            except Exception:
                pass
        kept = before.rstrip("\n")
        first = len(kept.splitlines()) + 3 if kept else 2  # "", ".. rvt::", "", code
        block = "\n".join("   " + row if row else "" for row in code.split("\n"))
        service.texts[path] = (kept + "\n\n" if kept else "") + ".. rvt::\n\n" + block + "\n"
        try:
            self.next += 1
            answers = self.server.handle({"jsonrpc": "2.0", "id": self.next, "method": method, "params": {
                "textDocument": {"uri": self.uri(path)},
                "position": {"line": first + line, "character": 3 + character}}})
        finally:
            if had:
                service.texts[path] = before
            else:
                service.texts.pop(path, None)
        result = next((a.get("result") for a in answers if a.get("id") == self.next), None)
        if result and method == "textDocument/hover" and result.get("range"):
            result["range"] = {key: {"line": at["line"] - first, "character": at["character"] - 3}
                               for key, at in result["range"].items()}
        if result and method == "textDocument/completion":
            for item in result.get("items", []):
                item.pop("textEdit", None)
        return {"result": result}


def lsp_session(ws, session):
    """The PageSession of a page's session"""
    sessions = current_app.config.setdefault("LSP_SESSIONS", {})
    now = time.monotonic()
    with _lsp_lock:
        for key in [k for k, found in sessions.items() if now - found.used > LSP_IDLE]:
            del sessions[key]
        key = (ws.id, session[:64])
        if key not in sessions:
            while len(sessions) >= LSP_SESSIONS:  # the longest idle goes
                del sessions[min(sessions, key=lambda k: sessions[k].used)]
            sessions[key] = PageSession(ws.root)
        found = sessions[key]
        found.used = now
    return found


# Routes, on the workspace blueprint


def register(bp, workspace_or_404, node_or_404):
    def target(id):
        """(workspace, the node the request's `path` names)"""
        if not editable():
            abort(403)
        ws = workspace_or_404(id)
        node = node_or_404(ws, request.args.get("path", ""))
        if node.is_root or node.is_dir():
            abort(404)
        return ws, node

    def body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            abort(400)
        return data

    @bp.route("/<path:id>/editor/render", methods=["POST"])
    def editor_render(id):
        """The HTML of one card, as edited"""
        if not editable():
            abort(403)
        workspace_or_404(id)
        data = body()
        card = as_card(data.get("card"))
        documents.ready()
        return jsonify(html=card_html(card, plain=bool(data.get("plain"))))

    @bp.route("/<path:id>/editor/state", methods=["GET"])
    def editor_state(id):
        """The hash of the file on disk, to tell when it changed"""
        _, node = target(id)
        return jsonify(hash=disk_hash(node.path))

    @bp.route("/<path:id>/editor/diff", methods=["POST"])
    def editor_diff(id):
        """Unified diff lines from the file on disk to the cards sent"""
        _, node = target(id)
        mine = sent_text(body())
        theirs = read(node.path) if node.is_file() else ""
        return jsonify(lines=list(difflib.unified_diff(
            theirs.splitlines(), mine.splitlines(), "on disk", "yours", lineterm="", n=3))[2:])

    @bp.route("/<path:id>/editor/save", methods=["POST"])
    def editor_save(id):
        ws, node = target(id)
        data = body()
        on_disk = disk_hash(node.path)
        if not data.get("force") and (data.get("hash") or None) != on_disk:
            return jsonify(hash=on_disk, changed=True), 409
        text = sent_text(data)
        write(node.path, text)
        if on_disk is None:  # a new file: show it in the tree
            expand_to(get_db(), ws.id, node.relative_path)
        current_app.logger.info("saved %s", node.path)
        return jsonify(hash=text_hash(text))

    # Files: new and clone answer with a file for the page to open
    # unsaved (nothing is on disk until it is saved); the rest act at once

    def refuse(message, status=409):
        response = jsonify(error=message)
        response.status_code = status
        abort(response)

    def new_file(ws, data, like=None):
        """The node of the file a request asks to make: `name` (default:
        from `title`) in `folder`. It must not be there yet."""
        title = " ".join(str(data.get("title") or "").split())
        if not title:
            refuse("Give it a title.", 400)
        name = str(data.get("name") or "").strip() or file_name(title)
        if not valid_entry_name(name):
            refuse("A file name can't have a folder in it, or start with a dot.", 400)
        if not name.endswith(".rst"):
            name += ".rst"
        folder = node_or_404(ws, str(data.get("folder") or ""))
        if not folder.is_dir():
            refuse("That folder isn't in this workspace.", 400)
        node = node_or_404(ws, str(folder.relative_path / name))
        if node.path.exists():
            refuse(f"{node.relative_path} is already there.")
        return node, title

    def workspace(id):
        if not editable():
            abort(403)
        return workspace_or_404(id)

    @bp.route("/<path:id>/editor/folders", methods=["GET"])
    def editor_folders(id):
        return jsonify(folders=folders(workspace(id).root))

    @bp.route("/<path:id>/editor/new", methods=["POST"])
    def editor_new(id):
        """A new script's skeleton, optionally for a requirement"""
        ws, data = workspace(id), body()
        node, title = new_file(ws, data)
        requirement, intro = str(data.get("requirement") or "").strip() or None, None
        if requirement:
            from .app import requirement_lookup
            from ..framework.rst import plain_text
            found = requirement_lookup(requirement)
            intro = plain_text(found.text) if found is not None and found.text else None
        return jsonify(drafted(node.path, node.relative_path,
                               skeleton(title, requirement, intro)))

    @bp.route("/<path:id>/editor/clone", methods=["POST"])
    def editor_clone(id):
        """A copy of the file `from`, under a new title"""
        ws, data = workspace(id), body()
        source = node_or_404(ws, str(data.get("from") or ""))
        if not source.is_file() or source.path.suffix != ".rst":
            refuse("Only scripts can be cloned.", 400)
        node, title = new_file(ws, data)
        return jsonify(drafted(node.path, node.relative_path,
                               retitled(read(source.path), title)))

    @bp.route("/<path:id>/editor/move", methods=["POST"])
    def editor_move(id):
        """Rename a file, or move it to another folder"""
        ws, data = workspace(id), body()
        source = node_or_404(ws, str(data.get("from") or ""))
        if source.is_root or not source.is_file():
            abort(404)
        name = str(data.get("name") or "").strip()
        if not valid_entry_name(name):
            refuse("Give it a file name, without a folder in it.", 400)
        folder = node_or_404(ws, str(data.get("folder") or ""))
        if not folder.is_dir():
            refuse("That folder isn't in this workspace.", 400)
        node = node_or_404(ws, str(folder.relative_path / name))
        if node.path.exists():
            refuse(f"{node.relative_path} is already there.")
        move_file(source.path, node.path)
        expand_to(get_db(), ws.id, node.relative_path)
        current_app.logger.info("moved %s to %s", source.path, node.path)
        return jsonify(path=str(node.relative_path))

    @bp.route("/<path:id>/editor/delete", methods=["POST"])
    def editor_delete(id):
        ws = workspace(id)
        node = node_or_404(ws, str(body().get("path") or ""))
        if node.is_root or not node.is_file():
            abort(404)
        delete_file(node.path)
        current_app.logger.info("deleted %s", node.path)
        return jsonify(ok=True)

    @bp.route("/<path:id>/editor/folder", methods=["POST"])
    def editor_folder(id):
        """A new folder, with a core.rst of its own if asked"""
        ws, data = workspace(id), body()
        name = str(data.get("name") or "").strip()
        if not valid_entry_name(name):
            refuse("Give the folder a name, without a folder in it.", 400)
        parent = node_or_404(ws, str(data.get("folder") or ""))
        if not parent.is_dir():
            refuse("That folder isn't in this workspace.", 400)
        node = node_or_404(ws, str(parent.relative_path / name))
        if node.path.exists():
            refuse(f"{node.relative_path} is already there.")
        create_folder(node.path)
        if data.get("core"):
            write(node.path / "core.rst",
                  titled(f"{name} definitions", over=False) + "\n\n.. rvt::\n   :definitions:\n")
        expand_to(get_db(), ws.id, node.relative_path, itself=True)
        return jsonify(path=str(node.relative_path))

    @bp.route("/<path:id>/lsp", methods=["POST"])
    def lsp(id):
        """The language server for the page's editor (PageSession), in
        cards. The body: `session`, the page's own; `sync`, files whose
        cards changed, each {path, cards, count}; `close`, paths no
        longer open; `request`, one {method (hover, completion or
        signature), path, card, line, character}; `start`, true on the
        page's first message. The answer:
        `problems`, {path: [problem]} for each file whose problems or
        cards changed, each problem with its card, `from` and `to` in it
        and its `line` in the file; `result`, the request's; `reset`
        when the session is new to the page (the server forgot it), which
        then starts again and sends every file."""
        ws, data = workspace(id), body()
        session = data.get("session")
        syncs, closes = data.get("sync") or [], data.get("close") or []
        if not isinstance(session, str) or not session or not isinstance(syncs, list) \
                or not isinstance(closes, list):
            abort(400)
        sent = []
        for sync in syncs:
            if not isinstance(sync, dict) or not isinstance(sync.get("path"), str) \
                    or not isinstance(sync.get("cards"), list):
                abort(400)
            count = sync.get("count")
            sent.append((sync["path"], [as_card(c) for c in sync["cards"]],
                         count if isinstance(count, int) else None))
        page = lsp_session(ws, session)
        answer = {}
        with page.lock:
            if data.get("start"):
                page.started = True
            elif not page.started:
                return jsonify(problems={}, reset=True)
            page.changed = set()
            for path in closes:
                if isinstance(path, str):
                    page.close(path)
            for path, found, count in sent:
                page.sync(path, found, count)
            if isinstance(data.get("request"), dict):
                result, reset = page.request(data["request"])
                if reset:
                    return jsonify(problems={}, reset=True)
                answer.update(result)
            answer["problems"] = page.problems()
        return jsonify(answer)

    @bp.route("/<path:id>/tabs", methods=["PUT"])
    def tabs(id):
        ws = workspace_or_404(id)
        data = body()
        paths = data.get("paths")
        if not isinstance(paths, list):
            abort(400)
        set_open_tabs(get_db(), ws.id, paths, data.get("active"))
        return jsonify(ok=True)
