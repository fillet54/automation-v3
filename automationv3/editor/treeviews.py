from pathlib import Path
from contextlib import closing
import json


class Treeview:
    def __init__(self, conn, id, factoryfn):
        self.conn = conn
        self.id = id
        self.factoryfn = factoryfn

        cursor = self.conn.execute(
            """
            SELECT opened, root
            FROM treeviews
            WHERE id = ?
        """,
            (self.id,),
        )
        row = cursor.fetchone()

        self.root = factoryfn(row[1], root=None)
        self.opened = [factoryfn(n, self.root) for n in json.loads(row[0])]

    @staticmethod
    def create(conn, root, factoryfn):
        with closing(conn.cursor()) as c:
            c.execute(
                """
                INSERT INTO treeviews(opened, root)
                VALUES (?, ?)
            """,
                (json.dumps([]), str(root)),
            )
            id = c.lastrowid
            conn.commit()
        return Treeview(conn, id, factoryfn)

    def node(self, id):
        return self.factoryfn(id, self.root)

    def toggle(self, node):
        if node in self.opened:
            self.opened.remove(node)
        else:
            self.opened.append(node)

        opened_as_str = [str(i) for i in self.opened]

        with closing(self.conn.cursor()) as c:
            c.execute(
                """
                UPDATE treeviews
                SET opened = ?
                WHERE id = ?
            """,
                (json.dumps(opened_as_str), self.id),
            )
            self.conn.commit()


class FileNode:
    """A file or directory within a root directory.

    Every node keeps a reference to its root node and refuses to be
    created for a path outside of that root."""

    def __init__(self, path, root=None):
        if root is None:
            self.root = self
            self.path = Path(path).resolve()
        else:
            self.root = root
            self.path = (root.path / path).resolve()
            if not self.path.is_relative_to(root.path):
                raise ValueError(f"'{self.path}' is not within '{root.path}'")

    def children(self):
        return [FileNode(child, self.root) for child in self.path.iterdir()]

    @property
    def name(self):
        return self.path.name

    @property
    def relative_path(self):
        return self.path.relative_to(self.root.path)

    @property
    def is_root(self):
        return self.path == self.root.path

    def is_dir(self):
        return self.path.is_dir()

    def is_file(self):
        return self.path.is_file()

    def __eq__(self, other):
        if isinstance(other, FileNode):
            return self.path == other.path
        return self.path == Path(other)

    def __hash__(self):
        return hash(self.path)

    def __lt__(self, other):
        return self.path < other.path

    def __str__(self):
        return str(self.path)

    def __repr__(self):
        return f"FileNode('{self.path}')"
