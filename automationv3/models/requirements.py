import sqlite3

class Requirement:
    def __init__(self, requirement_id, text, subsystem):
        self.requirement_id = requirement_id
        self.text = text
        self.subsystem = subsystem

class Requirements:
    def __init__(self, conn):
        self._conn = conn 
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS requirements (
                requirement_id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                subsystem TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def add(self, requirement):
        cursor = self._conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO requirements (text, requirement_id, subsystem) VALUES (?, ?, ?)",
                (requirement.text, requirement.requirement_id, requirement.subsystem)
            )
        except sqlite3.IntegrityError:
            cursor.execute(
                "UPDATE requirements SET text = ?, subsystem = ? WHERE requirement_id = ?",
                (requirement.text, requirement.subsystem, requirement.requirement_id)
            )
        self._conn.commit()
        cursor.close()

    def get_by_id(self, requirement_id):
        cursor = self._conn.execute("""
            SELECT requirement_id, text, subsystem
            FROM requirements
            WHERE requirement_id = ?
        """, (requirement_id,))
        row = cursor.fetchone()
        return Requirement(*row) if row else None

    def get_by_subsystem(self, subsystem):
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM requirements WHERE subsystem=?", (subsystem,))
        return [Requirement(*row) for row in cursor.fetchall()]

    def get_all(self):
        cursor = self._conn.execute("""
            SELECT requirement_id, text, subsystem
            FROM requirements
        """)
        return [Requirement(*row) for row in cursor.fetchall()]

    def get_subsystems(self):
        cursor = self._conn.cursor()
        cursor.execute("SELECT DISTINCT subsystem FROM requirements")
        return [row[0] for row in cursor.fetchall()]

    def remove(self, requirement_id):
        self._conn.execute("""
            DELETE FROM requirements
            WHERE requirement_id = ?
        """, (requirement_id,))
        self._conn.commit()
