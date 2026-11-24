"""Reading repositories with libgit2 (services/repo.py) gives what the
git command gives: checked against it on the same repositories"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from automationv3.services import repo, workspace
from automationv3.services.client import current_branch


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@x", *args], cwd=cwd,
                          capture_output=True, check=True).stdout.decode()


class TestRepo(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.top = self.tmp / "main"
        self.rvts = self.top / "tests" / "rvts"
        (self.rvts / "GDN").mkdir(parents=True)
        (self.rvts / "a.rst").write_text("a\n")
        (self.rvts / "GDN" / "b.rst").write_text("b\n")
        (self.rvts / "run.sh").write_text("#!/bin/sh\n")
        (self.rvts / "run.sh").chmod(0o755)
        (self.top / "outside.txt").write_text("o\n")
        (self.top / ".gitignore").write_text("*.log\n")
        git(self.top, "init", "-q", "-b", "master")
        git(self.top, "add", "--all")
        git(self.top, "commit", "-q", "-m", "one")

    def cli_edited(self, root):
        """What workspace.edited_files used to ask git"""
        changed = git(root, "diff", "--name-only", "--relative", "-z", "HEAD", "--", ".")
        untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z", "--", ".")
        return {p for p in (changed + untracked).split("\0") if p}

    def test_edited_files_are_what_git_says(self):
        self.assertEqual(workspace.edited_files(self.rvts), set())
        (self.rvts / "a.rst").write_text("changed\n")                # modified
        (self.rvts / "GDN" / "b.rst").unlink()                       # deleted
        (self.rvts / "new" / "deep").mkdir(parents=True)
        (self.rvts / "new" / "deep" / "c.rst").write_text("c\n")     # in a new folder
        (self.rvts / "staged.rst").write_text("s\n")
        git(self.rvts, "add", "staged.rst")                          # staged
        (self.rvts / "noise.log").write_text("x\n")                  # ignored
        (self.top / "outside.txt").write_text("elsewhere\n")         # not in the folder
        found = workspace.edited_files(self.rvts)
        self.assertEqual(found, {"a.rst", "GDN/b.rst", "new/deep/c.rst", "staged.rst"})
        self.assertEqual(found, self.cli_edited(self.rvts))

    def test_committed_text_and_checked_in(self):
        (self.rvts / "a.rst").write_text("in work\n")
        self.assertEqual(workspace.committed_text(self.rvts, "a.rst"), "a\n")
        self.assertEqual(workspace.committed_text(self.rvts, "GDN/b.rst"), "b\n")
        self.assertIsNone(workspace.committed_text(self.rvts, "nope.rst"))
        self.assertIsNone(workspace.committed_text(self.rvts, "GDN"))  # a folder
        out = workspace.checked_in(self.rvts, self.tmp / "cache")
        self.assertEqual(sorted(p.relative_to(out).as_posix() for p in out.rglob("*")),
                         ["GDN", "GDN/b.rst", "a.rst", "run.sh"])
        self.assertEqual((out / "a.rst").read_text(), "a\n")
        if os.name != "nt":
            self.assertTrue(os.access(out / "run.sh", os.X_OK))
        self.assertEqual(workspace.checked_in(self.rvts, self.tmp / "cache"), out)  # once

    def test_head_commit(self):
        self.assertEqual(workspace.head_commit(self.rvts), git(self.top, "rev-parse", "HEAD").strip())
        empty = self.tmp / "empty"
        git(self.tmp, "init", "-q", str(empty))
        self.assertIsNone(workspace.head_commit(empty))
        with self.assertRaises(ValueError):
            workspace.checked_in(empty, self.tmp / "cache")

    def test_worktrees_on_branches(self):
        git(self.top, "branch", "feature")
        git(self.top, "worktree", "add", "-q", str(self.tmp / "feature"), "feature")
        git(self.top, "worktree", "add", "-q", "--detach", str(self.tmp / "detached"))
        git(self.top, "branch", "gone")
        git(self.top, "worktree", "add", "-q", str(self.tmp / "gone"), "gone")
        shutil.rmtree(self.tmp / "gone")  # removed by hand: prunable
        git(self.top, "checkout", "-q", "-b", "topic")  # the main worktree moves to another branch
        for start in (self.rvts, self.tmp / "feature" / "tests" / "rvts"):
            self.assertEqual(workspace.find_worktrees(start), {
                "topic": self.rvts,
                "feature": self.tmp / "feature" / "tests" / "rvts",
            })
        self.assertEqual(workspace.scripts_folder(self.rvts), "tests/rvts")
        self.assertEqual(workspace.scripts_folder(self.top), "")

    def test_a_folder_outside_any_repository(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside)
        with self.assertRaises(repo.GitError):
            workspace.scripts_folder(outside)
        self.assertEqual(current_branch(outside), "")
        self.assertIsNone(workspace.head_commit(outside))

    def test_current_branch(self):
        self.assertEqual(current_branch(self.rvts), "master")
        git(self.top, "checkout", "-q", "--detach")
        self.assertEqual(current_branch(self.rvts), "HEAD")

    def test_dirty(self):
        found = repo.open_repo(self.top)
        self.assertFalse(repo.is_dirty(found))
        (self.top / "untracked.txt").write_text("u\n")
        self.assertFalse(repo.is_dirty(found))  # new files don't count
        (self.top / "outside.txt").write_text("changed\n")
        self.assertTrue(repo.is_dirty(found))


if __name__ == "__main__":
    unittest.main()
