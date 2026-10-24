"""The git host's webhook: something was pushed, so fetch

POST /hooks/git, from GitHub or Gitea (an HMAC-SHA256 signature of the
body, X-Hub-Signature-256 or X-Gitea-Signature) or GitLab (the secret
itself, X-Gitlab-Token), with the [git] webhook_secret from the settings.
Only a central server mirroring a remote has it.
"""

import hashlib
import hmac

from flask import Blueprint, current_app, jsonify, request

hooks = Blueprint("hooks", __name__)


def signed(secret, body, headers):
    """True if the request carries the secret, the way some git host signs"""
    key = secret.encode()
    expected = hmac.new(key, body, hashlib.sha256).hexdigest()
    github = headers.get("X-Hub-Signature-256", "")
    if github:
        return hmac.compare_digest(github, f"sha256={expected}")
    gitea = headers.get("X-Gitea-Signature", "")
    if gitea:
        return hmac.compare_digest(gitea, expected)
    gitlab = headers.get("X-Gitlab-Token", "")
    if gitlab:
        return hmac.compare_digest(gitlab.encode(), key)
    return False


@hooks.route("/hooks/git", methods=["POST"])
def git():
    git_settings = current_app.config["SETTINGS"].git
    if git_settings is None:
        return jsonify({"error": "This server doesn't mirror a git remote"}), 404
    if not git_settings.webhook_secret:
        return jsonify({"error": "Set [git] webhook_secret to take webhooks"}), 403
    if not signed(git_settings.webhook_secret, request.get_data(), request.headers):
        return jsonify({"error": "Bad signature"}), 403
    if request.headers.get("X-GitHub-Event") == "ping":
        return jsonify({"ok": True})
    from ..services.mirror import MirrorError
    try:
        current_app.config["WORKSPACES"].refresh()
    except MirrorError as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"fetched": True})
