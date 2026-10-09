"""A demo of Automation v3, set up in one command

`automation-v3 demo` builds a self-contained demo folder from a source
checkout and serves it:

    demo/
      .automation-v3-demo     marks the folder as safe to delete and rebuild
      workspace/master/       a git repository of the sample scripts, with
      workspace/branch1..3/   worktrees for the other workspaces
      automationv3.db         the sample requirements
      reports/
      environments/           the sim and bench environments' work directories
      worker.json             the local worker's config, hosting them
      docs/                   this project's documentation, built

The sample scripts, requirements and documentation sources come from the
checkout (test/data and docs/), so the demo needs an editable install
(`pip install -e .`).
"""

import json
import shutil
import subprocess
import sys
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .framework.requirement import Requirement
from .services.database import connect, init_db
from .services.requirements import models as requirements
from .services.requirements import rst_source

SOURCE = Path(__file__).resolve().parent.parent
SAMPLES = SOURCE / "test" / "data"
DOCS_SOURCE = SOURCE / "docs"
MARKER = ".automation-v3-demo"
BRANCHES = ("branch1", "branch2", "branch3")
ENVIRONMENTS = ("sim", "bench")


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
    """The checkout's sample data, or DemoError if this isn't a checkout"""
    if not (SAMPLES / "rvts").is_dir():
        raise DemoError(
            "The demo needs the sample scripts from a source checkout: clone the "
            "repository and install it with `pip install -e .`")


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
    """A git repository of the sample scripts on master, with a worktree
    per other branch. Returns the repository."""
    repo = path / "master"
    shutil.copytree(SAMPLES / "rvts", repo / "rvts")
    git("init", "-q", cwd=repo)
    git("symbolic-ref", "HEAD", "refs/heads/master", cwd=repo)
    git("add", "--all", cwd=repo)
    git("commit", "-q", "-m", "Sample scripts", cwd=repo)
    for branch in BRANCHES:
        git("branch", branch, cwd=repo)
        git("worktree", "add", "-q", str(path / branch), branch, cwd=repo)
    return repo


def parse_requirement(line):
    """A Requirement from a line of text ending in its id, e.g.
    "The brakes shall ... [VMCBRA00001]." or "... [AP-1.3]". The
    subsystem is the letters after VMC (BRA), or before the first dash
    (AP)."""
    line = line.strip()
    start = line.rfind("[")
    id = line[start + 1:line.rfind("]")].strip()
    if id.startswith("VMC"):
        subsystem = id.split("VMC")[1].split("0")[0].strip()
    else:
        subsystem = id.split("-")[0].strip()
    return Requirement(id=id, text=line[:start].strip(), subsystem=subsystem)


def read_requirements(path):
    """The Requirements in a file: an rst requirements document (see
    services/requirements/rst_source.py), or text with one requirement
    per line, its id at the end in brackets"""
    path = Path(path)
    if path.suffix == ".rst":
        return rst_source.parse(path.read_text())
    lines = [line for line in path.read_text().splitlines() if line.strip()]
    return [parse_requirement(line) for line in lines]


def sample_requirement_files():
    """The sample requirements: the line-per-requirement file, then every
    rst document in test/data/requirements"""
    return [SAMPLES / "sample_requirements.txt",
            *sorted((SAMPLES / "requirements").glob("*.rst"))]


def load_requirements(db_path, sources=None):
    found = [r for path in (sources or sample_requirement_files())
             for r in read_requirements(path)]
    with closing(connect(db_path)) as conn:
        init_db(conn)
        requirements.insert(conn, found)


def write_worker_config(path):
    """A worker config hosting the sample environments, working under `path`"""
    config = {"environments": {
        name: {"workdir": str(path / "environments" / name)} for name in ENVIRONMENTS
    }}
    file = path / "worker.json"
    file.write_text(json.dumps(config, indent=2) + "\n")
    return file


def build_docs(out):
    """Build the documentation into `out`. Returns `out`, or None (saying
    why) if Sphinx isn't installed or the build failed."""
    try:
        import sphinx  # noqa: F401
        import sphinx_rtd_theme  # noqa: F401
    except ImportError:
        print("   Docs not built: install Sphinx with `pip install -e \".[docs]\"`")
        return None
    result = subprocess.run(
        [sys.executable, "-m", "sphinx", "-b", "html", "-q",
         "-d", str(out.parent / "doctrees"), str(DOCS_SOURCE), str(out)],
        capture_output=True, text=True)
    if result.returncode != 0:
        print("   Docs not built:\n" + (result.stderr or result.stdout).strip())
        return None
    return out


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
    log("   Workspace: the sample scripts, on master and three branches")
    load_requirements(demo.db_path)
    log("   Requirements: the sample set, loaded")
    if docs:
        log("   Building the documentation...")
        demo.docs = build_docs(path / "docs" / "html")
    return demo
