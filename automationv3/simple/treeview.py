import operator as op
import sqlite3
from contextlib import closing

# =========================================================
#                        Models 
# =========================================================

class FilesystemNode:
    """Node representing a file or directory

    This node uses the a filesystem to store 
    it's state.
    """
    def __init__(self, path, root=None):
        self.root = root or path
        self.name = path.name
        self.rel_path == path.relative_to(root) 
        self.abs_path = (self.root / self.rel_path).resolve()

    def is_root(self):
        return self.rel_path == Path(".")

    def children(self):
        if self.abs_path.is_dir():
            return [
                type(self)(path, self.root)
                for path in self.abs_path.iterdir()
            ]
        return []

    def _compare(self, other, op):
        if not hasattr(other, "abs_path"):
            return NotImplemented
        return op(str(self.abs_path), str(other.abs_path))

    def __eq__(self, other): return self._compare(other, op.eq)
    def __lt__(self, other): return self._compare(other, op.lt)
    def __le__(self, other): return self._compare(other, op.le)
    def __gt__(self, other): return self._compare(other, op.gt)
    def __ge__(self, other): return self._compare(other, op.ge)
    

class FileSystemTreeView:
    """Treeview of a filesystem

    root path and opened paths are stored in sqlite
    """

    def __init__(self, db, id=None, root=None):
        assert id or root, "One of id or root must be provided"

        self.db = db
        self.id = id
        self.root = root.resolve()
        self.opened = []

        if id is None:
            self.id = self.create()
        else:
            self.read()

    def toggle(self, node):
        if node in self.opened:
            self.opened.remove(node)
        else:
            self.opened.append(node)
        self.update()

    # Persistent methods
    @staticmethod
    def ensure_db(db):
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS treeviews(
                id INTEGER PRIMARY KEY,
                opened JSON,
                root TEXT
                """
            )

    def create(self):
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute(
                """
                INSERT INTO treeviews(opened, root)
                VALUES (?, ?)
                RETURNING id
                """, 
                (json.dumps([]), str(self.root))
            )

    def read(self):
        with closing(sqlite3.connect(self.db)) as conn:
            cursor = conn.execute(
                """
                SELECT opened, root
                FROM treeviews
                WHERE id = ?
                """,
                (self.id,)
            )
            row = cursor.fetchone()
        self.root = FilesystemNode(row[1], root=None)
        self.opened = [FilesystemNode(n, self.root)
                       for n in json.loads(row[0])]

    def update(self):
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute(
                """
                UPDATE treeviews
                SET opened = ?
                WHERE id = ?
                """, 
                (json.dumps(self.opened))
            )

# =========================================================
#                         Views
# =========================================================

treeviews = Blueprint("treeviews", __name__, template_folder=template_root)

@treeviews.app_template_filter()
def is_dir(paths):
    return [p for p in paths if p.is_dir()]


@treeviews.app_template_filter()
def is_file(paths):
    return [p for p in paths if p.is_file()]


@treeviews.app_template_filter()
def as_id(path):
    return re.sub(r"[^a-zA-Z0-9]", "--", str(path))


@treeviews.route("/tree", defaults={"path": ""}, methods=["GET"])
@treeviews.route("/tree/<path:path>", methods=["GET", "POST"])
def tree(path):
    workspace_id = request.args.get("workspace_id")
    workspace = get_workspaces(workspace_id)
    fstree = workspace.filesystem_tree()

    if path == "":
        path = workspace.root

    # ensure path is relative to our root
    if not (workspace.root / path).resolve().is_relative_to(workspace.root):
        abort(404)

    path = (workspace.root / path).resolve().relative_to(workspace.root)
    if request.method == "POST":
        fstree.toggle(path)

    return render_template(
        "partials/treeitem.html",
        workspace=workspace,
        node=fstree.node(path),
        opened=fstree.opened,
    )
