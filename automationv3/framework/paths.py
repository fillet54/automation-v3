"""Paths relative to a scripts root, as the app names them

Scripts, core.rst files, load orders, closures, runs, the editor's tabs
and URLs all name a file by its path relative to its scripts root with
"/" between folders, on every platform. On Windows, str() of a Path
(or of path.relative_to(root)) uses "\\" instead, so a path made that
way names nothing here: pass it through `posix` first.
"""

from pathlib import PurePath


def posix(path):
    """`path` (a str or a PurePath) with "/" between its parts.

    A backslash is taken as a separator wherever the path came from (a
    Windows client may send one to a server on Linux): no script or
    folder name holds one."""
    if isinstance(path, PurePath):
        path = path.as_posix()
    return str(path).replace("\\", "/")
