from pathlib import Path
import re

class FileNode:
    """
    A class representing a node in a filesystem tree structure.
    
    This class models files and directories as nodes in a tree, allowing
    for easy traversal and manipulation of filesystem hierarchies. Each
    node keeps track of its own path and a reference to the root node
    of the tree it belongs to.
    """

    def __init__(self, path, root=None):
        if not isinstance(path, Path):
            path = Path(path)

        if root is None:
            self.root = self
            self.path = path.resolve()
        else:
            if not isinstance(root, FileNode):
                raise TypeError("root must be a FileNode instance.")
            self.root = root
            self.path = (self.root.path / path).resolve()

            # Ensure the path is within the root path
            if not self.path.is_relative_to(self.root.path):
                raise ValueError(f"Path '{self.path}' is not within root path '{self.root.path}'.")


    def children(self):
        try:
            return [FileNode(child, root=self.root) for child in self.path.iterdir()]
        except PermissionError:
            # Handle cases where the directory cannot be accessed
            return []

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
        elif isinstance(other, Path):
            return self.path == other
        elif isinstance(other, str):
            return str(self.path) == other
        else:
            return False

    def __str__(self):
        return str(self.path)

    def __repr__(self):
        return f"FileNode(path='{self.path}')"

    def __hash__(self):
        return hash(self.path)

    def __lt__(self, other):
        if isinstance(other, FileNode):
            return self.path < other.path
        elif isinstance(other, (Path, str)):
            return str(self.path) < str(other)
        else:
            return NotImplemented

    def __gt__(self, other):
        if isinstance(other, FileNode):
            return self.path > other.path
        elif isinstance(other, (Path, str)):
            return str(self.path) > str(other)
        else:
            return NotImplemented



class Workspace:
    def __init__(self, name, root_path, expanded_nodes=None):
        self.name = name
        self.root_node = FileNode(root_path) 
        self.expanded_nodes = expanded_nodes

        if expanded_nodes is None:
            self.expanded_nodes = set()


    def toggle_node(self, path):
        node = FileNode(path, root=self.root_node)

        # Verify valid node
        if str(node.relative_path) != path:
            raise ValueError

        if node in self.expanded_nodes:
            self.expanded_nodes.remove(node)
            print("close")
        else:
            self.expanded_nodes.add(node)
            print("open")

        return node


    def __repr__(self):
        return f"Workspace(root='{self.root_node.name}')"


# Data
# TODO: Persist
expanded_nodes = set() 

# Views

from flask import Blueprint, render_template, request, abort, make_response, current_app

workspace = Blueprint("workspace", __name__)

def get_workspace(name):
    workspace_root = current_app.config["workspace_root"]
    workspace_path = workspace_root / name / "rvts"
    
    if workspace_path.exists() and workspace_path.is_dir():
        return Workspace(name, workspace_path, expanded_nodes)

    raise ValueError

def get_workspaces():
    workspace_root = current_app.config["workspace_root"]
    return [get_workspace(child.name)
            for child in workspace_root.iterdir() 
            if child.is_dir()]



@workspace.route("/<name>", methods=["GET"])
def index(name):

    try:
        workspace = get_workspace(name)
        workspaces = get_workspaces()
        return render_template("workspace.html", workspace=workspace, workspaces=workspaces)
    except ValueError:
        abort(404)


@workspace.route("/<name>/expand", methods=["POST"])
def expand_tree(name):

    try:
        workspace = get_workspace(name)
        path = request.args.get("path")
        node = workspace.toggle_node(path)
        return render_template("partials/treeview.html", workspace=workspace, node=node)
    except ValueError:
        abort(404)


    


# Filters 
@workspace.app_template_filter()
def is_dir(paths):
    return [p for p in paths if p.is_dir()]

@workspace.app_template_filter()
def is_file(paths):
    return [p for p in paths if p.is_file()]

@workspace.app_template_filter()
def as_id(path):
    """Used to turn path into html compliant id"""
    return re.sub(r"[^a-zA-Z0-9]", "--", str(path))

