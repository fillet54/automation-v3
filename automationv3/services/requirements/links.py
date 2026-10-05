"""Which scripts reference which requirements, per workspace

Scripts reference requirements with :req:`ID` in their documentation.
The links are read statically and cached in sqlite; `refresh` re-reads
only scripts whose modification time changed.
"""

from pathlib import Path

from ...framework.closure import CORE, requirement_refs


def scripts(root):
    """Every script under `root`, as paths relative to it"""
    root = Path(root)
    return sorted(
        str(p.relative_to(root).as_posix())
        for p in root.rglob("*.rvt")
        if p.name != CORE and p.is_file()
    )


def refresh(conn, workspace, root):
    """Bring the index for `workspace` up to date with the files on disk"""
    root = Path(root)
    known = dict(
        conn.execute(
            "SELECT script, st_mtime FROM indexed_scripts WHERE workspace = ?",
            (workspace,),
        ).fetchall()
    )
    present = scripts(root)
    with conn:
        for script in set(known) - set(present):
            forget(conn, workspace, script)
        for script in present:
            mtime = (root / script).stat().st_mtime
            if known.get(script) == mtime:
                continue
            forget(conn, workspace, script)
            try:
                refs = requirement_refs((root / script).read_text())
            except Exception:
                refs = []  # unreadable scripts link to nothing
            conn.executemany(
                "INSERT INTO requirement_links VALUES (?, ?, ?)",
                [(workspace, script, ref) for ref in refs],
            )
            conn.execute(
                "INSERT INTO indexed_scripts VALUES (?, ?, ?)",
                (workspace, script, mtime),
            )


def forget(conn, workspace, script):
    for table in ("indexed_scripts", "requirement_links"):
        conn.execute(
            f"DELETE FROM {table} WHERE workspace = ? AND script = ?",
            (workspace, script),
        )


def scripts_by_requirement(conn, workspace):
    """requirement id -> sorted list of scripts referencing it"""
    linked = {}
    for requirement_id, script in conn.execute(
        """
        SELECT requirement_id, script FROM requirement_links
        WHERE workspace = ? ORDER BY script
        """,
        (workspace,),
    ):
        linked.setdefault(requirement_id, []).append(script)
    return linked


def requirements_of(conn, workspace, script):
    return [
        row[0]
        for row in conn.execute(
            """
            SELECT requirement_id FROM requirement_links
            WHERE workspace = ? AND script = ? ORDER BY 1
            """,
            (workspace, script),
        )
    ]
