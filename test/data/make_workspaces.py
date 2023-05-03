
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
import subprocess

data_dir = Path(__file__).resolve().parent
rvt_src_dir = data_dir / 'rvts'
worktree_dir = data_dir / 'git_repos'
main_git_dir = worktree_dir / 'master'

if main_git_dir.exists():
    print(f"Files already exist!!!\nPlease delete {str(main_git_dir)} to recreate")
    sys.exit(-1) 

subprocess.check_output(['git', 'init', str(main_git_dir)])

# Copy files for master
shutil.copytree(rvt_src_dir, main_git_dir / 'rvts')
subprocess.check_output(['git', 'add', '--all'], cwd=main_git_dir)
subprocess.check_output(['git', 'commit', '-m', "Initial Commit"], cwd=main_git_dir)


worktrees = ['branch1', 'branch2', 'branch3']
for worktree in worktrees:
    worktree_path = worktree_dir / worktree
    subprocess.check_output(['git', 'branch', worktree], cwd=main_git_dir)
    subprocess.check_output(['git', 'worktree', 'add', worktree_path, worktree], cwd=main_git_dir)




