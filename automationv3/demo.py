"""A demo of Automation v3, set up in one command

`automation-v3 demo` builds a self-contained demo folder from the Apollo
lunar module example that ships with the package, and serves it:

    demo/
      .automation-v3-demo     marks the folder as safe to delete and rebuild
      workspace/master/       a git repository of the example scripts, with
      workspace/branch1..3/   worktrees for the other workspaces
      automationv3.db         the example's requirements, imported from exports/
      exports/                the example's DOORS history: one export per run
      reports/
      environments/           the sim and lms environments' work directories
      worker.json             the local worker's config, hosting them
      builds/                 the lunar module's build repository (uploaded builds)
      local-build/            a build "made on this machine", ready to upload
      docs/                   this project's documentation, built

The example lives in automationv3/examples/apollo. The documentation is
built only from a source checkout, which has docs/.
"""

import json
import os
import shutil
import subprocess
import sys
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .services.database import connect, init_db
from .services.requirements import export, links, store, suspects
from .services.requirements import models as requirements
from .services.workspace import find_worktrees

SAMPLES = Path(__file__).resolve().parent / "examples" / "apollo"
SAMPLE_EXPORTS = SAMPLES / "doors"
DOCS_SOURCE = Path(__file__).resolve().parent.parent / "docs"  # in a source checkout
MARKER = ".automation-v3-demo"
BRANCHES = ("branch1", "branch2", "branch3")
ENVIRONMENTS = ("sim", "lms")


class DemoError(Exception):
    pass


@dataclass
class Demo:
    path: Path
    db_path: Path
    workspace: Path
    reports: Path
    config: Path
    docs: Path = None  # the built HTML, if it was built


def check_source():
    """DemoError if the example isn't installed with the package"""
    if not (SAMPLES / "rvts").is_dir():
        raise DemoError(f"The Apollo example is missing from this installation ({SAMPLES})")


def clear(path):
    """Delete an earlier demo at `path`, refusing to delete anything else"""
    if path.exists():
        if not path.is_dir():
            raise DemoError(f"{path} is a file, not a demo folder")
        if not (path / MARKER).exists() and any(path.iterdir()):
            raise DemoError(
                f"{path} already exists and isn't a demo folder. Pick another "
                "--path, or delete it yourself.")
        shutil.rmtree(path)
    path.mkdir(parents=True)
    (path / MARKER).write_text("Made by `automation-v3 demo`; rebuilt on each run.\n")


def git(*args, cwd):
    subprocess.run(
        ["git", "-c", "user.name=Automation v3 demo", "-c", "user.email=demo@localhost",
         *args],
        cwd=cwd, check=True, capture_output=True)


def make_workspace(path):
    """A git repository of the sample scripts (in its rvts/ folder) on
    master, with a worktree per other branch. Returns master's scripts
    folder, the workspace path."""
    repo = path / "master"
    shutil.copytree(SAMPLES / "rvts", repo / "rvts")
    git("init", "-q", cwd=repo)
    git("symbolic-ref", "HEAD", "refs/heads/master", cwd=repo)
    git("add", "--all", cwd=repo)
    git("commit", "-q", "-m", "Sample scripts", cwd=repo)
    for branch in BRANCHES:
        git("branch", branch, cwd=repo)
        git("worktree", "add", "-q", str(path / branch), branch, cwd=repo)
    return repo / "rvts"


def apply_edit(tree, edit):
    """Apply one edit of the sample history to `tree` (spec -> path -> text)"""
    files = tree[edit["spec"]]
    if "remove" in edit or "move" in edit:
        id = edit.get("remove") or edit["move"]
        path = next(p for p, text in files.items() if f".. requirement:: {id}\n" in text)
        start = files[path].index(f".. requirement:: {id}\n")
        rest = files[path][start:].split("\n")
        end = next((n for n, line in enumerate(rest[1:], 1)
                    if line and not line.startswith(" ")), len(rest))
        block = "\n".join(rest[:end]).rstrip() + "\n"
        files[path] = (files[path][:start] + "\n".join(rest[end:])).rstrip() + "\n"
        if "move" in edit:
            files[edit["to"]] = files[edit["to"]].rstrip() + "\n\n" + block
    elif "append" in edit:
        files[edit["file"]] = files[edit["file"]].rstrip() + "\n\n" + edit["append"]
    else:
        if files[edit["file"]].count(edit["old"]) != 1:
            raise DemoError(f"sample history: {edit['spec']}/{edit['file']} doesn't "
                            f"have {edit['old']!r} exactly once")
        files[edit["file"]] = files[edit["file"]].replace(edit["old"], edit["new"])


def write_sample_exports(out):
    """Write the example's DOORS history (examples/apollo/doors) as export folders
    under `out`, one per run, as the exporter would. Returns their paths,
    oldest first."""
    history = json.loads((SAMPLE_EXPORTS / "history.json").read_text())
    tree = {key: {p.relative_to(SAMPLE_EXPORTS / "specs" / key).as_posix(): p.read_text()
                  for p in sorted((SAMPLE_EXPORTS / "specs" / key).rglob("*.rst"))}
            for key in history["specs"]}
    folders = []
    for run in history["runs"]:
        for edit in run.get("edits", []):
            apply_edit(tree, edit)
        folder = Path(out) / run["name"]
        entries = []
        versions = [(key, None) for key in history["specs"]]
        versions += list(run.get("baselines", {}).items())
        for key, baseline in versions:
            root = f"{key}@{baseline}" if baseline else key
            for name, text in tree[key].items():
                (folder / root / name).parent.mkdir(parents=True, exist_ok=True)
                (folder / root / name).write_text(text)
            entries.append({"key": key, **history["specs"][key], "root": root,
                            "attributes": history["attributes"],
                            "doors": {"module": f"/Mission/{key}", "id_source": "Req ID"},
                            **({"baseline": baseline} if baseline else {})})
        manifest = {"format": 1, "exporter": {"name": "sample", "version": "1"},
                    "exported_at": f"{run['name']}T02:00:00Z", "specs": entries,
                    "baseline_sets": [{"name": name, "specs": pins}
                                      for name, pins in run.get("sets", {}).items()]}
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        folders.append(folder)
    return folders


def load_requirements(db_path, exports, workspace=None):
    """Import export folders, in order, into the database at `db_path`.
    With a `workspace` (a scripts folder in a git worktree), its scripts' links are first seen
    after the first export, as if the scripts had been written then, so
    later changes to their requirements make them suspect."""
    with closing(connect(db_path)) as conn:
        init_db(conn)
        for n, folder in enumerate(exports):
            store.import_export(conn, export.read(folder))
            if n == 0 and workspace:
                for name, root in find_worktrees(workspace).items():
                    links.refresh(conn, name, root)
                    context, _ = requirements.workspace_context(conn, root)
                    suspects.sync_scripts(conn, name, context)


RELEASE_BRANCH = "branch1"


def pin_release_branch(workspace, branch=RELEASE_BRANCH, context="set:Release 1"):
    """Make `branch` a release branch: its automation.json says it verifies
    `context`"""
    root = find_worktrees(workspace)[branch]
    (root / "automation.json").write_text(
        json.dumps({"requirements": context}, indent=2) + "\n")
    git("add", "automation.json", cwd=root)
    git("commit", "-q", "-m", f"Verify {context}", cwd=root)


def write_worker_config(path):
    """The example's worker config (examples/apollo/worker.json), each
    environment working under `path`"""
    config = json.loads((SAMPLES / "worker.json").read_text())
    for name, params in config["environments"].items():
        params["workdir"] = str(path / "environments" / name)
    file = path / "worker.json"
    file.write_text(json.dumps(config, indent=2) + "\n")
    return file


LOCAL_BUILD = {"revision": "LUM131-fix",
               "flags": {"extended_missions": True, "prop_capacity_from_load": True}}


def set_up_builds(path):
    """The lunar module's build repository (AUTOMATION_LM_BUILDS, for this
    process and the worker in it), and a local build of LUM131 with its
    defect fixed, for the local client to find and upload. Returns the
    local build's folder."""
    repo = path / "builds"
    repo.mkdir()
    os.environ["AUTOMATION_LM_BUILDS"] = str(repo)
    local = path / "local-build"
    local.mkdir()
    (local / "luminary.json").write_text(json.dumps(LOCAL_BUILD, indent=2) + "\n")
    return local


def build_docs(out):
    """Build the documentation into `out`. Returns `out`, or None (saying
    why) if Sphinx isn't installed or the build failed."""
    if not (DOCS_SOURCE / "conf.py").exists():
        print("   Docs not built: they are built from a source checkout's docs/")
        return None
    try:
        import sphinx  # noqa: F401
    except ImportError:
        print("   Docs not built: Sphinx isn't installed (`pip install sphinx`)")
        return None
    result = subprocess.run(
        [sys.executable, "-m", "sphinx", "-b", "html", "-q",
         "-d", str(out.parent / "doctrees"), str(DOCS_SOURCE), str(out)],
        capture_output=True, text=True)
    if result.returncode != 0:
        print("   Docs not built:\n" + (result.stderr or result.stdout).strip())
        return None
    return out


def existing(path):
    """The demo already set up at `path` (by `setup`), as it is"""
    path = Path(path).resolve()
    if not (path / MARKER).exists():
        raise DemoError(f"{path} isn't a demo folder")
    if (path / "builds").is_dir():
        os.environ["AUTOMATION_LM_BUILDS"] = str(path / "builds")
    docs = path / "docs" / "html"
    return Demo(path=path, db_path=path / "automationv3.db",
                workspace=path / "workspace" / "master" / "rvts", reports=path / "reports",
                config=path / "worker.json",
                docs=docs if (docs / "index.html").exists() else None)


def setup(path, docs=True, log=print):
    """Build a fresh demo at `path`, deleting an earlier one"""
    check_source()
    path = Path(path).resolve()
    log(f"   Setting up the demo in {path}")
    clear(path)
    demo = Demo(path=path, db_path=path / "automationv3.db",
                workspace=make_workspace(path / "workspace"),
                reports=path / "reports", config=write_worker_config(path))
    demo.reports.mkdir()
    log("   Workspace: the Apollo example's scripts, on master and three branches")
    local = set_up_builds(path)
    log(f"   Builds: the lunar module's build repository is builds/; local-build/ holds "
        f"LUM131 with its defect fixed ({local / 'luminary.json'})")
    pin_release_branch(demo.workspace)
    load_requirements(demo.db_path, write_sample_exports(path / "exports"), demo.workspace)
    log("   Requirements: the example's DOORS history, imported from exports/; "
        f"{RELEASE_BRANCH} verifies Release 1")
    if docs:
        log("   Building the documentation...")
        demo.docs = build_docs(path / "docs" / "html")
    return demo
