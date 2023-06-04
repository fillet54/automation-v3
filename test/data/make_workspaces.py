
'''
Workspaces are going to be represented by Git worktrees.

For now the repository layout will be hard coded to a single folder
within each worktree

    ./rvts

This scripts takes the sample RVTs in ./rvts and creates 3 worktrees

'''


import sys
import shutil
from pathlib import Path
from functools import partial
import subprocess


check_output_no_stderr = partial(subprocess.check_output, stderr=subprocess.DEVNULL)

def create_repo(path):
    check_output_no_stderr(['git', 'init', path])
    check_output_no_stderr(['git', 'add', '--all'], cwd=path)
    check_output_no_stderr(['git', 'commit', '-m', "Initial Commit"], cwd=path)
    

def create_worktree(gitdir, workdir):
    worktree = workdir.name
    check_output_no_stderr(['git', 'branch', worktree], cwd=gitdir)
    check_output_no_stderr(['git', 'worktree', 'add', workdir, worktree], cwd=gitdir)

if __name__ == '__main__':
    datadir = Path(__file__).resolve().parent
    rvtdir = datadir / 'rvts'
    gitdir = datadir / 'git_repos' / 'master'

    if gitdir.exists():
        print(f"Files already exist!!!\nPlease delete {str(gitdir)} to recreate")
        sys.exit(-1) 

    # Setup initial master branch with content
    shutil.copytree(rvtdir, gitdir / 'rvts')
    create_repo(gitdir)


    worktrees = ['branch1', 'branch2', 'branch3']
    for worktree in worktrees:
        workdir = gitdir.parent / worktree
        create_worktree(gitdir, workdir)


