"""The API the local client calls (services/client.py)

JSON over HTTP, with the client's device token (`Authorization: Bearer
av3u_...`), except the two calls that get one:

    POST /api/login/start   {email, device}   -> {code, interval, expires_in}
                            emails a link that approves the device
    POST /api/login/poll    {code}            -> 200 {token, email} once approved,
                                                 202 while waiting, 410 if expired
    POST /api/logout                          revokes the token it came with
    GET  /api/whoami                          -> {email, admin, central}
    GET  /api/requirements?id=..&context=..   -> {id: requirement or null}
    GET  /api/environments                    -> {environment: [live worker urls]}
    GET  /api/uuts                            -> {uut: [{id, digest}], oldest first}
    POST /api/scratch       {workspace, files, scripts, environment, variation,
                             uut_versions, device}
                            -> {runs: [{id, script, environment, variation, url}]}
    GET  /api/scratch/<id>                    -> the run: outcome, status, ...
    GET  /api/scratch/<id>/events?after=N     -> {events: [...], finished}

Scratch uploads are a closure's files (path -> text) from the client's
worktree, as they are on disk. They run only in scratch, never in a report.
"""

import shutil
import socket
import tempfile
from dataclasses import asdict
from pathlib import Path, PurePosixPath

from flask import Blueprint, abort, current_app, jsonify, request

from ..framework.planning import build_plan
from ..framework.uut import uut_types
from ..services import accounts
from ..services import jobs as models
from ..services.reports import store
from ..services.requirements import models as requirement_models
from .auth import (central, current_user, external_url, is_admin, owner_email,
                   send_link, settings)
from .db import get_db
from .jobs import live_environments

api = Blueprint("api", __name__)

# What one scratch upload may carry
MAX_FILES = 500
MAX_BYTES = 10 * 1024 * 1024
POLL_SECONDS = 2


def body():
    return request.get_json(silent=True) or {}


def error(message, status=400):
    return jsonify({"error": message}), status


# Signing a client in


@api.route("/login/start", methods=["POST"])
def login_start():
    if not central():
        return error("This server is single-user: it needs no sign-in", 404)
    data = body()
    device = (data.get("device") or "").strip() or "a client"
    try:
        code, link = accounts.start_device_login(get_db(), settings().auth,
                                                 data.get("email", ""), device)
    except accounts.AccountError as e:
        return error(str(e))
    send_link(accounts.normal_email(data["email"]), link, device=device)
    return jsonify({"code": code, "interval": POLL_SECONDS,
                    "expires_in": settings().auth.link_minutes * 60})


@api.route("/login/poll", methods=["POST"])
def login_poll():
    if not central():
        return error("This server is single-user: it needs no sign-in", 404)
    try:
        token = accounts.poll_device_login(get_db(), body().get("code"))
    except accounts.AccountError as e:
        return error(str(e), 410)
    if token is None:
        return jsonify({"pending": True}), 202
    user = accounts.token_for(get_db(), token).user
    return jsonify({"token": token, "email": user.email})


@api.route("/logout", methods=["POST"])
def logout():
    """Revoke the device token this request came with"""
    from flask import g
    token = g.get("api_token")
    if token is not None:
        accounts.revoke_token(get_db(), token.id, user=current_user())
    return jsonify({"revoked": token is not None})


@api.route("/whoami", methods=["GET"])
def whoami():
    user = current_user()
    return jsonify({"email": user.email if central() else None, "admin": is_admin(),
                    "central": central(), "server": socket.gethostname()})


# What the client shows and offers


def requirement_json(requirement):
    return asdict(requirement) if requirement is not None else None


@api.route("/requirements", methods=["GET"])
def requirements():
    """The requirements asked for, in a context (default trunk)"""
    context = request.args.get("context") or None
    try:
        found = {id: requirement_json(requirement_models.find_by_id(get_db(), id, context))
                 for id in request.args.getlist("id")}
    except requirement_models.ContextError as e:
        return error(str(e))
    latest = get_db().execute("SELECT MAX(id) FROM imports").fetchone()[0]
    return jsonify({"requirements": found, "import": latest})


@api.route("/environments", methods=["GET"])
def environments():
    return jsonify(live_environments())


@api.route("/uuts", methods=["GET"])
def uuts():
    return jsonify({name: [asdict(v) for v in cls().list_versions()]
                    for name, cls in sorted(uut_types().items())})


# Scratch runs from the client's worktree


def safe_path(path):
    """`path` if it is a relative path inside a folder, else None"""
    parts = PurePosixPath(path or "")
    if not path or parts.is_absolute() or ".." in parts.parts or "\\" in path:
        return None
    return str(parts)


def write_files(folder, files):
    for path, text in files.items():
        dest = folder / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)


def run_json(run):
    from .reports import run_status
    return {
        "id": run["id"],
        "script": run["script"],
        "environment": run.get("environment"),
        "variation": (run.get("variation") or {}).get("name"),
        "outcome": run.get("outcome"),
        "status": run_status(run),
        "queued_by": run.get("queued_by"),
        "url": external_url("reports.run", report_id=models.SCRATCH, run_id=run["id"]),
    }


@api.route("/scratch", methods=["POST"])
def scratch():
    """Run uploaded files in scratch"""
    data = body()
    files, scripts = data.get("files") or {}, data.get("scripts") or []
    if not isinstance(files, dict) or not files or not scripts:
        return error("files (path -> text) and scripts are required")
    if len(files) > MAX_FILES or sum(len(t) for t in files.values()) > MAX_BYTES:
        return error(f"Too much to upload: at most {MAX_FILES} files, "
                     f"{MAX_BYTES // 1024 // 1024} MB", 413)
    clean = {safe_path(p): t for p, t in files.items()}
    if None in clean or not all(isinstance(t, str) for t in clean.values()):
        return error("File paths must be relative, inside the workspace, and text")
    if any(safe_path(s) not in clean for s in scripts):
        return error("Every script must be among the files")

    environment, variation = data.get("environment"), data.get("variation")
    folder = Path(tempfile.mkdtemp(prefix="upload-"))
    try:
        write_files(folder, clean)
        plan = build_plan(
            data.get("workspace") or "", folder, [safe_path(s) for s in scripts],
            scratch=True,
            environments=[environment] if environment else None,
            versions=data.get("uut_versions") or {},
            variations={f"{s}::{variation}" for s in scripts} if variation else None)
        try:
            run_ids = models.queue_scratch(
                get_db(), current_app.config["REPORTS_PATH"], plan, models.UPLOADED,
                owner=owner_email(),
                **({"device": data["device"]} if data.get("device") else {}))
        except models.QueueError as e:
            return jsonify({"errors": e.errors}), 400
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    root = current_app.config["REPORTS_PATH"]
    runs = [store.load_run(root, models.SCRATCH, id) for id in run_ids]
    return jsonify({"runs": [run_json(r) for r in runs]}), 201


def scratch_run(run_id):
    return store.load_run(current_app.config["REPORTS_PATH"], models.SCRATCH, run_id) \
        or abort(404)


@api.route("/scratch/<run_id>", methods=["GET"])
def scratch_status(run_id):
    return jsonify(run_json(scratch_run(run_id)))


@api.route("/scratch/<run_id>/events", methods=["GET"])
def scratch_events(run_id):
    """The run's events after the first `after`, to follow it as it runs"""
    run = scratch_run(run_id)
    events = store.read_events(current_app.config["REPORTS_PATH"], models.SCRATCH, run_id)
    after = request.args.get("after", 0, type=int)
    return jsonify({"events": events[after:], "finished": run.get("outcome") is not None,
                    "outcome": run.get("outcome")})


@api.errorhandler(404)
def not_found(e):
    return error("Not found", 404)
