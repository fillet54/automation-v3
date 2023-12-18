import sqlite3
from contextlib import contextmanager
from pathlib import Path
from enum import IntEnum


class Status(IntEnum):
    WAITING = 0
    IN_WORK = 1
    DONE = 2


class SQLPriorityQueue:
    def __init__(self, filename=None, memory=False, **kwargs):
        if memory or filename is None or filename == ":memory:":
            self.conn = sqlite3.connect(":memory:", isolation_level=None, **kwargs)
        elif isinstance(filename, (str, Path)):  # pragma: no cover
            self.conn = sqlite3.connect(str(filename), isolation_level=None, **kwargs)
            self.conn.execute("PRAGMA journal_mode = 'WAL';")
            self.conn.execute("PRAGMA temp_store = 2;")
            self.conn.execute("PRAGMA synchronous = 1;")
            self.conn.execute(f"PRAGMA cache_size = {-1 * 64_000};")
        else:  # pragma: no cover
            assert filename is not None
            self.conn = filename
            self.conn.isolation_level = None

        self.conn.row_factory = sqlite3.Row

        with self.transaction():
            self.conn.execute(
                """CREATE TABLE IF NOT EXISTS Queue
                ( message TEXT NOT NULL,
                  message_id TEXT,
                  status INTEGER,
                  in_time INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                  lock_time INTEGER,
                  done_time INTEGER,
                  priority INTEGER DEFAULT 0 )
                """
            )

            self.conn.execute("CREATE INDEX IF NOT EXISTS TIdx ON Queue(message_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS SIdx ON Queue(status)")

    def put(self, message):
        """
        Insert a new message
        """

        with self.transaction(mode="IMMEDIATE"):
            rid = self.conn.execute(
                """
                INSERT INTO Queue  (message,
                                    message_id,
                                    status,
                                    in_time,
                                    lock_time,
                                    done_time,
                                    priority)
                VALUES (:message,
                        lower(hex(randomblob(16))),
                        0,
                        strftime('%s','now'),
                        NULL,
                        NULL,
                        (SELECT COALESCE( MAX( priority ), 0 ) + 1
                         FROM Queue
                         WHERE STATUS = 0))
                RETURNING
                message_id, priority
                """,
                {"message": message},
            ).fetchone()

        return dict(rid)

    def pop(self):
        # RETURNING could be used if sqlite version >= 3.35
        # but for compatibility we will just do this in three steps
        with self.transaction(mode="IMMEDIATE"):
            message = self.conn.execute(
                """
                SELECT * FROM Queue
                WHERE rowid = (SELECT min(priority) FROM Queue
                               WHERE status = 0)
                """
            ).fetchone()

            if message is None:
                return None

            # If we found a record we need to lock it
            self.conn.execute(
                """
                UPDATE Queue
                SET status = 1, lock_time = strftime('%s','now')
                WHERE message_id = :message_id AND status = 0
                """,
                {"message_id": message["message_id"]},
            )

            # finally get the updated row
            message = self.conn.execute(
                """
                SELECT * FROM Queue
                WHERE message_id = :message_id
                """,
                {"message_id": message["message_id"]},
            ).fetchone()

            return dict(message)

    def update_priority(self, message_id, priority):
        with self.transaction(mode="IMMEDIATE"):
            # First shift all lower priorities down by 1
            # I wonder if I really need to do this vs just
            # subtracting 1 from the min priority
            # and use in_time in the rank over
            self.conn.execute(
                """
                UPDATE Queue
                SET priority = priority + 1
                WHERE priority >= :priority
                """,
                {"priority": priority},
            )
            # Next we raise the priority of the target message
            rid = self.conn.execute(
                """
                UPDATE Queue
                SET priority = :priority
                WHERE message_id = :message_id
                """,
                {"message_id": message_id, "priority": priority},
            ).lastrowid
        return rid

    def peek(self):
        "Show next message to be popped."
        value = self.conn.execute(
            """
            SELECT * FROM Queue
            WHERE priority = (SELECT min(priority) FROM QUEUE
                           WHERE status = 0)
            ORDER BY rowid LIMIT 1
            """
        ).fetchone()
        return dict(value)

    def get(self, message_id=None, status=Status.WAITING, limit=100):
        "Get a message by its `message_id` if supplied or all up to limit"

        if message_id is not None:
            value = self.conn.execute(
                """
                SELECT *
                FROM Queue
                WHERE message_id = :message_id
                """,
                {"message_id": message_id},
            ).fetchone()
            return dict(value) if value is not None else value
        elif isinstance(status, int):
            value = self.conn.execute(
                """
                SELECT *,
                       RANK() OVER ( ORDER BY priority ) depth
                FROM Queue
                WHERE status = :status
                ORDER BY depth
                LIMIT :limit
                """,
                {"limit": limit, "status": status},
            )
            return [dict(v) for v in value]

    def done(self, message_id):
        """
        Mark message as done.
        If executed multiple times, `done_time` will be
        the last time this function is called.
        """

        rid = self.conn.execute(
            """
            UPDATE Queue
            SET status = 2,  done_time = strftime('%s','now')
            WHERE message_id = :message_id
            """,
            {"message_id": message_id},
        ).lastrowid
        return rid

    def qsize(self):
        return next(self.conn.execute("SELECT COUNT(*) FROM Queue WHERE status != 2"))[
            0
        ]

    def empty(self):
        value = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM Queue WHERE status = 0"
        ).fetchone()
        return not bool(value["cnt"])

    @contextmanager
    def transaction(self, mode="DEFERRED"):
        if mode not in {"DEFERRED", "IMMEDIATE", "EXCLUSIVE"}:  # pragma: no cover
            raise ValueError(f"Transaction mode '{mode}' is not valid")
        self.conn.execute(f"BEGIN {mode}")
        try:
            # Yield control back to the caller.
            yield
        except BaseException as e:  # pragma: no cover
            self.conn.rollback()  # Roll back all changes if an exception occurs.
            raise e
        else:
            self.conn.commit()


__all__ = ["SQLPriorityQueue", "Status"]
