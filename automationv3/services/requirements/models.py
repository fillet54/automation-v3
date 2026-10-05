"""Requirements stored in sqlite"""

from ...framework.requirement import Requirement

__all__ = ["Requirement", "find_by_id", "find_all", "subsystems", "insert"]


def find_by_id(conn, id):
    row = conn.execute(
        "SELECT id, text, subsystem FROM requirements WHERE id = ?", (id,)
    ).fetchone()
    return Requirement(*row) if row else None


def find_all(conn, subsystem=None):
    if subsystem:
        rows = conn.execute(
            "SELECT id, text, subsystem FROM requirements WHERE subsystem = ?",
            (subsystem,),
        )
    else:
        rows = conn.execute("SELECT id, text, subsystem FROM requirements")
    return [Requirement(*row) for row in rows]


def subsystems(conn):
    rows = conn.execute("SELECT DISTINCT subsystem FROM requirements ORDER BY 1")
    return [row[0] for row in rows]


def insert(conn, requirements):
    with conn:
        conn.executemany(
            "INSERT INTO requirements(id, text, subsystem) VALUES (?, ?, ?)",
            [(r.id, r.text, r.subsystem) for r in requirements],
        )
