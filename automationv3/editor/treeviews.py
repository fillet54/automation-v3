from pathlib import Path


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


def expanded_nodes(conn, workspace_id, root):
    """The set of nodes under `root` that are expanded in the tree view"""
    rows = conn.execute(
        "SELECT path FROM expanded_nodes WHERE workspace_id = ?", (workspace_id,)
    )
    return {FileNode(row[0], root) for row in rows}


def toggle_expanded(conn, workspace_id, node):
    params = (workspace_id, str(node.relative_path))
    with conn:
        deleted = conn.execute(
            "DELETE FROM expanded_nodes WHERE workspace_id = ? AND path = ?", params
        ).rowcount
        if not deleted:
            conn.execute(
                "INSERT INTO expanded_nodes(workspace_id, path) VALUES (?, ?)", params
            )
