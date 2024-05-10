import subprocess

from flask import Blueprint, render_template


commitlog = Blueprint("commitlog", __name__, template_folder="templates")


def get_files_for_commit(commit_hash):
    cmd = ["git", "show", "--pretty=", "--name-only", commit_hash]
    output = subprocess.check_output(cmd).decode("utf-8")
    return output.splitlines()


def get_author_for_commit(commit_hash):
    cmd = ["git", "show", '--pretty="%an"', "-s", commit_hash]
    output = subprocess.check_output(cmd).decode("utf-8")
    return output.strip().strip('"')


def get_commit_date(commit_hash):
    cmd = ["git", "show", '--pretty="%cd"', "-s", commit_hash]
    output = subprocess.check_output(cmd).decode("utf-8")
    return output.strip().strip('"')


def get_message_for_commit(commit_hash):
    cmd = ["git", "show", '--pretty="%B"', "-s", commit_hash]
    output = subprocess.check_output(cmd).decode("utf-8")
    return output.strip().strip('"')


def get_commit_log():
    cmd = ["git", "log", '--format="%H"']
    output = subprocess.check_output(cmd).decode("utf-8")

    commits = {}

    for commit_hash in output.splitlines():
        commit_hash = commit_hash.strip('"')
        commits[commit_hash] = {
            "files": get_files_for_commit(commit_hash),
            "author": get_author_for_commit(commit_hash),
            "date": get_commit_date(commit_hash),
            "message": get_message_for_commit(commit_hash),
        }
        commits[commit_hash]["title"] = commits[commit_hash]["message"].split("\n")[0]

    return commits


def get_versions():
    return [
        "VERSION_1",
        "VERSION_2",
        "VERSION_3",
        "VERSION_4",
        "VERSION_5",
    ]


@commitlog.route("/")
def list():
    commits = get_commit_log()
    versions = get_versions()
    return render_template("commitlog.html", commitlog=commits, versions=versions)


@commitlog.route("/details/<hash>")
def details(hash):
    commits = get_commit_log()
    commit = commits[hash]
    return render_template("partials/commitlog_detail.html", commit=commit)
