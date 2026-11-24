"""Reading git repositories in process, through libgit2 (pygit2)

Starting git once per question is slow, on Windows above all, and a page
asks several (which worktrees there are, what is edited, what is checked
in). These answer the same questions without a process each.

A Repository is opened for each call: opening one is cheap, and a
pygit2 Repository shouldn't be shared between the server's threads.
Fetching and cloning stay with the git command (services/mirror.py), so
the user's credential helpers and SSH setup keep working.
"""

import os
import shutil
import stat
import tempfile
from pathlib import Path, PurePosixPath

import pygit2


class GitError(RuntimeError):
    """Not a repository, or something in it couldn't be read"""


def open_repo(path):
    """The repository (or worktree) `path` is in. Raises GitError if it
    isn't in one."""
    found = pygit2.discover_repository(str(path))
    if found is None:
        raise GitError(f"{path} isn't in a git repository")
    try:
        return pygit2.Repository(found)
    except pygit2.GitError as e:
        raise GitError(f"{path}: {e}") from None


def workdir(repo):
    """The top folder of `repo`'s worktree"""
    if repo.workdir is None:
        raise GitError(f"{repo.path} is a bare repository")
    return Path(repo.workdir).resolve()


def prefix(path, repo=None):
    """Where `path` is in its worktree: its folder relative to the
    worktree's top, with "/" between folders ("" for the top itself)"""
    repo = repo or open_repo(path)
    relative = Path(path).resolve().relative_to(workdir(repo)).as_posix()
    return "" if relative == "." else relative


def head_branch(repo):
    """The branch HEAD is on (refs/heads/...), even with no commit yet;
    None for a detached HEAD"""
    try:
        target = repo.lookup_reference("HEAD").target
    except (KeyError, pygit2.GitError):
        return None
    return target if isinstance(target, str) and target.startswith("refs/heads/") else None


def head_commit(repo):
    """The commit id HEAD is at, or None if there is none yet"""
    if repo.head_is_unborn:
        return None
    try:
        return str(repo.head.target)
    except pygit2.GitError:
        return None


def common_repo(repo):
    """The repository a worktree belongs to (`repo` itself, unless it is a
    linked worktree)"""
    common = Path(repo.path) / "commondir"
    if not common.is_file():
        return repo
    target = common.read_text(encoding="utf-8").strip()
    return pygit2.Repository(str((Path(repo.path) / target).resolve()))


def worktrees(path):
    """[(worktree top folder, branch ref or None)] for every worktree of
    the repository `path` is in, the main one first (unless bare)"""
    main = common_repo(open_repo(path))
    found = []
    if not main.is_bare:
        found.append((workdir(main), head_branch(main)))
    for name in main.list_worktrees():
        try:
            tree = main.lookup_worktree(name)
            if tree.is_prunable or not Path(tree.path).is_dir():
                continue
            found.append((Path(tree.path).resolve(), head_branch(pygit2.Repository(tree.path))))
        except pygit2.GitError:
            continue  # half made or half removed: leave it out
    return found


# What changed, and what is checked in

CHANGED = ~(pygit2.enums.FileStatus.CURRENT | pygit2.enums.FileStatus.IGNORED)


def changed_paths(repo, under=""):
    """Paths under folder `under` (relative to it, "/" between folders)
    whose files differ from HEAD: modified, staged, deleted or new and not
    ignored"""
    start = under.strip("/") + "/" if under.strip("/") else ""
    return {path[len(start):] for path, flags in repo.status(untracked_files="all").items()
            if flags & CHANGED and path.startswith(start)}


def is_dirty(repo):
    """True if a tracked file differs from HEAD (new files don't count)"""
    return any(flags & CHANGED for flags in repo.status(untracked_files="no").values())


def tree_at(repo, commit, folder=""):
    """The tree of `folder` in `commit` (an id), or None if the commit has
    no such folder"""
    try:
        tree = repo[commit].peel(pygit2.Tree)
        if folder.strip("/"):
            tree = repo[tree[folder.strip("/")].id]
    except (KeyError, ValueError, pygit2.GitError):
        return None
    return tree if isinstance(tree, pygit2.Tree) else None


def file_text(repo, commit, path):
    """The text of file `path` ("/" between folders) in `commit`, or None
    if it isn't there"""
    try:
        blob = repo[repo[commit].peel(pygit2.Tree)[str(PurePosixPath(path))].id]
    except (KeyError, ValueError, pygit2.GitError):
        return None
    if not isinstance(blob, pygit2.Blob):
        return None
    return blob.data.decode("utf-8")


def write_tree(repo, tree, out):
    """Write the files of `tree` under folder `out`, as git archive would
    (a submodule is an empty folder; a symbolic link is made if the system
    lets us, else left out)"""
    out.mkdir(parents=True, exist_ok=True)
    for entry in tree:
        target = out / entry.name
        if entry.filemode == pygit2.enums.FileMode.TREE:
            write_tree(repo, repo[entry.id], target)
        elif entry.filemode == pygit2.enums.FileMode.COMMIT:
            target.mkdir(exist_ok=True)
        elif entry.filemode == pygit2.enums.FileMode.LINK:
            try:
                os.symlink(repo[entry.id].data.decode("utf-8"), target)
            except (OSError, NotImplementedError):
                pass
        else:
            target.write_bytes(repo[entry.id].data)
            if entry.filemode == pygit2.enums.FileMode.BLOB_EXECUTABLE:
                target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def extract_atomic(repo, tree, out, cache, prefix="extract-", under=""):
    """Write `tree` (None: nothing) into folder `out` (at its folder
    `under`, if given) atomically, under `cache`, tolerating another
    writer finishing first"""
    out, cache = Path(out), Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=prefix, dir=cache))
    try:
        if tree is not None:
            write_tree(repo, tree, work.joinpath(*PurePosixPath(under).parts) if under else work)
        try:
            os.replace(work, out)
        except OSError:
            if not out.is_dir():
                raise
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out
