"""Snippets: named pieces of code to start from

A folder may hold one ``snippets.rst``. Each titled rvt block in it is a
snippet: the title is its name, the paragraph just before the block (if
any) says what it is for, and the block's code is what is inserted::

    Booting
    -------

    Boots the LM for a mission and start point, and checks it is ready.

    .. rvt:: Boot and check

       (StartLM {:mission #{mission} :start #{start}})
       (Verify (lm-ready? #{mission} #{start}))

``#{name}`` marks a field to fill in; fields of the same name are filled
in together, and the editor steps through them with Tab (CodeMirror's
snippet fields). ``#{}`` is a stop with nothing in it. They are edn sets, so the
block still reads, and the page renders it like any other block.

A script sees the snippets of every snippets.rst from the root down to
its folder, as it sees core.rst files; a deeper one's snippet replaces a
shallower one of the same name. snippets.rst files are neither scripts
nor definitions: nothing in them runs, and they aren't checked beyond
reading.
"""

import re
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath

from docutils import nodes

from . import source
from .language import ancestor_files

SNIPPETS = "snippets.rst"
FIELD = re.compile(r"#\{([^{}]*)\}")


@dataclass
class Snippet:
    name: str
    description: str
    code: str
    path: str  # the snippets.rst it is from, relative to the root
    line: int  # its block's first line there

    def as_dict(self):
        return {**asdict(self), "text": plain(self.code)}


def is_snippets(path):
    return PurePosixPath(path).name == SNIPPETS


def plain(code):
    """The code with its fields as their names, and the cursor mark gone:
    what to insert where fields can't be stepped through"""
    return FIELD.sub(lambda m: m.group(1).strip(), code)


def _description(block):
    """The paragraph right before `block` in its parent, as text"""
    parent = block.parent
    at = parent.index(block)
    for sibling in reversed(parent.children[:at]):
        if isinstance(sibling, nodes.paragraph):
            return " ".join(sibling.astext().split())
        if isinstance(sibling, (nodes.comment, nodes.system_message)):
            continue
        break
    return ""


def read(text, path=SNIPPETS):
    """(snippets, problems) of a snippets.rst's `text`; problems are
    source.Problem"""
    tree = source.parse(text, path)
    found, problems, names = [], [], {}
    for block in source.walk(tree):
        if not isinstance(block, source.rvt_block):
            continue
        if block.error is not None:
            problems.append(block.error)
        name = block.title
        if not name:
            problems.append(source.Problem(
                "A snippet needs a name: give its block a title (.. rvt:: Name)",
                source.edn.Span(block.line_start, 0, block.line_start, 1, path)))
            continue
        if name in names:
            problems.append(source.Problem(
                f"Another snippet is already called {name} (line {names[name]})",
                source.edn.Span(block.line_start, 0, block.line_start, 1, path)))
            continue
        names[name] = block.line_start
        found.append(Snippet(name, _description(block), block.code.strip("\n"),
                             path, block.line_start))
    return found, problems


def chain(path):
    """The snippets.rst paths from the root down to `path`'s folder (a
    file's, or `path` itself if `is_dir`)"""
    return ancestor_files(path, SNIPPETS)


def collect(root, path, texts=None):
    """The snippets a file at `path` (relative to `root`) can use, by
    name, deepest first, then by name. `texts` ({path: text}) stands in
    for what is on disk, as for files being edited."""
    texts = texts or {}
    by_name = {}
    for found in chain(path):
        text = texts.get(found)
        if text is None:
            file = root / found
            if not file.is_file():
                continue
            try:
                text = file.read_text()
            except (OSError, UnicodeDecodeError):
                continue
        for snippet in read(text, found)[0]:
            by_name[snippet.name] = snippet
    depth = {p: n for n, p in enumerate(chain(path))}
    return sorted(by_name.values(), key=lambda s: (-depth[s.path], s.name.lower()))
