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
from html import escape
from pathlib import Path, PurePosixPath

from flask import abort, current_app, jsonify, request

from ..framework import cards as card_model
from ..framework.cards import Card, PROSE, RVT, SOURCE
from . import documents
from .db import get_db
from .jobs import workspaces

FIELDS = ("kind", "source", "index", "text", "title", "definitions", "table",
          "variations", "code")
MAX_TABS = 40


def editable():
    """Files are edited where they are worktrees on this machine, and
    never on the central server"""
    from . import auth
    return bool(getattr(workspaces(), "editable", True)) and not auth.central()


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
    """How many lines of a prose card's text are its heading"""
    lines = text.lstrip("\n").splitlines()
    return 3 if lines and card_model.is_adornment(lines[0]) else 2


def failed(text, error):
    return (f'<div class="ed-unreadable">{escape(str(error))}</div>'
            f'<pre class="ui-pre">{escape(text)}</pre>')


def card_html(card, diagnostics=(), plain=False):
    """A card as the page shows it when it isn't being edited. An rvt
    card shows as its steps do on a script's page, with the `diagnostics`
    (see workspace.diagnostic_views) about its lines."""
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
    """What the page keeps of a card, and sends back to save"""
    data = {name: getattr(card, name) for name in FIELDS}
    data["level"] = card.level
    return data


def drafted(path, relative, text):
    """A file that isn't on disk yet, for the page to open as a tab with
    unsaved edits: its path, and its cards with their HTML"""
    plain = path.suffix != ".rst"
    found = file_cards(path, text)
    documents.ready()
    return {"path": str(relative), "count": len(found),
            "cards": [{"data": payload(card), "html": card_html(card, plain=plain)}
                      for card in found]}


def card_views(path, text, diagnostics=()):
    """[{kind, html, data}] for the cards of a file's text"""
    plain = path.suffix != ".rst"
    return [{"kind": card.kind, "html": card_html(card, diagnostics, plain),
             "data": json.dumps(payload(card))}
            for card in file_cards(path, text)]


def as_card(data):
    """The Card of what the page sent, or abort(400)"""
    if not isinstance(data, dict) or data.get("kind") not in (PROSE, RVT, SOURCE):
        abort(400)
    source, index = data.get("source"), data.get("index")
    variations = data.get("variations") or []
    if isinstance(variations, str):
        variations = variations.split(",")
    try:
        ok = ((source is None or isinstance(source, str))
              and (index is None or isinstance(index, int))
              and all(isinstance(v, str) for v in variations))
    except TypeError:
        ok = False
    if not ok:
        abort(400)
    return Card(data["kind"], source, index=index if source is not None else None,
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
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "wb") as f:
            f.write(text.encode("utf-8"))
        if path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        else:
            os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


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
        found += [str((Path(folder) / n).relative_to(root)) for n in names]
    return sorted(found)


def expand_to(conn, workspace_id, relative, itself=False):
    """Open the tree down to `relative` (and the folder `itself`)"""
    parts = PurePosixPath(relative).parts
    parts = parts if itself else parts[:-1]
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO expanded_nodes(workspace_id, path) VALUES (?, ?)",
            [(workspace_id, str(PurePosixPath(*parts[:n]))) for n in range(1, len(parts) + 1)])


# Open tabs, per workspace


def open_tabs(conn, workspace_id):
    """([path], the active path or None), in tab order"""
    rows = conn.execute("SELECT path, active FROM open_tabs WHERE workspace_id = ? "
                        "ORDER BY position", (workspace_id,)).fetchall()
    return [r[0] for r in rows], next((r[0] for r in rows if r[1]), None)


def set_open_tabs(conn, workspace_id, paths, active):
    paths = list(dict.fromkeys(p for p in paths if isinstance(p, str) and p))[:MAX_TABS]
    with conn:
        conn.execute("DELETE FROM open_tabs WHERE workspace_id = ?", (workspace_id,))
        conn.executemany(
            "INSERT INTO open_tabs(workspace_id, path, position, active) VALUES (?, ?, ?, ?)",
            [(workspace_id, p, n, int(p == active)) for n, p in enumerate(paths)])


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
        if "/" in name or "\\" in name or name.startswith("."):
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
            from ..framework import rst as script_rst
            from ..services.requirements.rst_source import plain_text
            found = script_rst.find_requirement(requirement)
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
        if not name or "/" in name or "\\" in name or name.startswith("."):
            refuse("Give it a file name, without a folder in it.", 400)
        folder = node_or_404(ws, str(data.get("folder") or ""))
        if not folder.is_dir():
            refuse("That folder isn't in this workspace.", 400)
        node = node_or_404(ws, str(folder.relative_path / name))
        if node.path.exists():
            refuse(f"{node.relative_path} is already there.")
        source.path.rename(node.path)
        expand_to(get_db(), ws.id, node.relative_path)
        current_app.logger.info("moved %s to %s", source.path, node.path)
        return jsonify(path=str(node.relative_path))

    @bp.route("/<path:id>/editor/delete", methods=["POST"])
    def editor_delete(id):
        ws = workspace(id)
        node = node_or_404(ws, str(body().get("path") or ""))
        if node.is_root or not node.is_file():
            abort(404)
        node.path.unlink()
        current_app.logger.info("deleted %s", node.path)
        return jsonify(ok=True)

    @bp.route("/<path:id>/editor/folder", methods=["POST"])
    def editor_folder(id):
        """A new folder, with a core.rst of its own if asked"""
        ws, data = workspace(id), body()
        name = str(data.get("name") or "").strip()
        if not name or "/" in name or "\\" in name or name.startswith("."):
            refuse("Give the folder a name, without a folder in it.", 400)
        parent = node_or_404(ws, str(data.get("folder") or ""))
        if not parent.is_dir():
            refuse("That folder isn't in this workspace.", 400)
        node = node_or_404(ws, str(parent.relative_path / name))
        if node.path.exists():
            refuse(f"{node.relative_path} is already there.")
        node.path.mkdir()
        if data.get("core"):
            write(node.path / "core.rst",
                  titled(f"{name} definitions", over=False) + "\n\n.. rvt::\n   :definitions:\n")
        expand_to(get_db(), ws.id, node.relative_path, itself=True)
        return jsonify(path=str(node.relative_path))

    @bp.route("/<path:id>/tabs", methods=["PUT"])
    def tabs(id):
        ws = workspace_or_404(id)
        data = body()
        paths = data.get("paths")
        if not isinstance(paths, list):
            abort(400)
        set_open_tabs(get_db(), ws.id, paths, data.get("active"))
        return jsonify(ok=True)
