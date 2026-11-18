"""Git repositories and worktrees for tests: a workspace is a git
worktree with its scripts in ./rvts"""

import subprocess
from functools import partial

check_output_no_stderr = partial(subprocess.check_output, stderr=subprocess.DEVNULL)


def create_repo(path):
    check_output_no_stderr(['git', 'init', path])
    check_output_no_stderr(['git', 'add', '--all'], cwd=path)
    check_output_no_stderr(['git', 'commit', '-m', "Initial Commit"], cwd=path)


def create_worktree(gitdir, workdir):
    worktree = workdir.name
    check_output_no_stderr(['git', 'branch', worktree], cwd=gitdir)
    check_output_no_stderr(['git', 'worktree', 'add', workdir, worktree], cwd=gitdir)
