"""Who is asking: sign-in pages, sessions, API tokens and the checks

In single-user mode (no [auth] in the settings) everyone is the local
admin and nothing asks to sign in. In central mode every page needs a
signed-in user: a browser session (by an emailed link), or a client's
API token (`Authorization: Bearer av3u_...`). The worker API takes a
worker's token instead (`av3w_...`), and a few endpoints are open: the
sign-in pages themselves, static files, the git webhook and the
client's device sign-in.

Sessions are cookies (HttpOnly, SameSite=Lax, so other sites can't post
with them).
"""

import functools
import socket
from urllib.parse import urlsplit

from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from ..services import accounts, mail
from .db import get_db

auth = Blueprint("auth", __name__)

COOKIE = "av3_session"

# The single-user mode's one user
LOCAL_USER = accounts.User(0, "local@localhost")

# Endpoints anyone may call
OPEN = {"auth.login", "auth.link", "auth.signed_out", "static", "paper_ui.static",
        "hooks.git", "api.login_start", "api.login_poll"}

# Endpoints only a worker token may call
WORKER_API = {"jobqueue.register_worker", "jobqueue.list_jobs", "jobqueue.claim_job",
              "jobqueue.start_job", "jobqueue.release_job", "jobqueue.post_events",
              "jobqueue.attach_file", "jobqueue.complete_job"}


def settings():
    return current_app.config["SETTINGS"]


def accounts_enabled():
    """Accounts are on: the settings have [auth]"""
    return settings().central


def current_user():
    """The signed-in user (the local user in single-user mode), or None"""
    return g.get("user")


def is_admin(user=None):
    user = user or current_user()
    if user is None:
        return False
    if not accounts_enabled():
        return True
    return settings().auth.is_admin(user.email)


def owner_email():
    """What to record as the owner of something made now: the user's
    email, or None in single-user mode (nobody owns anything)"""
    user = current_user()
    return user.email if accounts_enabled() and user is not None else None


def can_change(report):
    """May the current user change `report`? (see services/reports/access.py)"""
    from ..services.reports import access
    if not accounts_enabled():
        return True
    user = current_user()
    return user is not None and access.can_change(report, user.email, is_admin(user))


def everyone():
    """Is the page showing everyone's things (?who=everyone), not just the
    current user's? Always, on a single-user server."""
    return not accounts_enabled() or request.args.get("who") == "everyone"


def mine_only():
    """The email to filter a page's list by, or None to show everything"""
    return None if everyone() else owner_email()


def bearer():
    header = request.headers.get("Authorization", "")
    kind, _, secret = header.partition(" ")
    return secret.strip() if kind.lower() == "bearer" else None


def wants_json():
    return (request.path.startswith("/api/") or request.is_json
            or bearer() is not None
            or request.accept_mimetypes.best == "application/json")


def load_user():
    """Before each request: who is asking, and may they?"""
    g.user, g.api_token, g.worker_token = None, None, None
    if not accounts_enabled():
        g.user = LOCAL_USER
        return None
    conn = get_db()
    secret = bearer()
    if secret:
        token = accounts.token_for(conn, secret)
        if token is not None and token.kind == accounts.WORKER_TOKEN:
            g.worker_token = token
        elif token is not None:
            g.api_token, g.user = token, token.user
    else:
        g.session_token = request.cookies.get(COOKIE)
        g.user = accounts.session_user(conn, g.session_token,
                                       settings().auth.session_days)

    endpoint = request.endpoint or ""
    if endpoint in OPEN:
        return None
    if endpoint in WORKER_API:
        if g.worker_token is None:
            return jsonify({"error": "A worker token is required"}), 401
        return None
    if g.user is None:
        if wants_json():
            return jsonify({"error": "Sign in first"}), 401
        return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
    return None


def keep_cookie(response):
    """After each request: a used session's cookie lives as long again"""
    token = g.get("session_token")
    if accounts_enabled() and token and g.get("user") is not None:
        set_cookie(response, token)
    return response


def set_cookie(response, token):
    days = settings().auth.session_days
    response.set_cookie(COOKIE, token, max_age=days * 86400, httponly=True,
                        samesite="Lax", secure=secure())


def secure():
    base = settings().base_url
    return base.startswith("https:") if base else request.is_secure


def admin_required(view):
    @functools.wraps(view)
    def check(*args, **kwargs):
        if not is_admin():
            abort(403)
        return view(*args, **kwargs)
    return check


def safe_next(target, fallback=None):
    """`target` if it is a path on this site, else `fallback` (default: home page)"""
    parts = urlsplit(target or "")
    if not target or parts.scheme or parts.netloc or not target.startswith("/") \
            or target.startswith("//"):
        return fallback if fallback is not None else url_for("index")
    return target


def base_url():
    """The server's external base URL: settings().base_url, else this request's host URL"""
    return settings().base_url or request.host_url.rstrip("/")


def external_url(endpoint, **values):
    """A link to put in an email: on base_url when it is set"""
    base = settings().base_url
    if base:
        return base + url_for(endpoint, **values)
    return url_for(endpoint, _external=True, **values)


def send_link(email, token, device=None, next=None):
    values = {"token": token}
    if next and next != url_for("index"):
        values["next"] = next
    link = external_url("auth.link", **values)
    mail.send_sign_in(settings().smtp, email, link, settings().auth.link_minutes,
                      device=device, brand=current_app.config.get("UI_BRAND", "automation"))


def init_app(app):
    app.register_blueprint(auth)
    app.before_request(load_user)
    app.after_request(keep_cookie)

    @app.context_processor
    def who():
        user = current_user()
        shown = None
        if accounts_enabled() and user is not None:
            shown = {"name": user.email, "role": "Admin" if is_admin(user) else None,
                     "initials": user.email[:2].upper()}
        return {"current_user": user, "ui_user": shown, "central": accounts_enabled(),
                "is_admin": is_admin(user) if user else False}


# Pages


@auth.route("/auth/login", methods=["GET", "POST"])
def login():
    if not accounts_enabled():
        return redirect(url_for("index"))
    next = safe_next(request.values.get("next"))
    if request.method == "GET":
        if current_user() is not None:
            return redirect(next)
        return render_template("auth/login.html", next=next, email="", error=None)
    email = request.form.get("email", "")
    try:
        token = accounts.request_sign_in(get_db(), settings().auth, email)
    except accounts.AccountError as e:
        return render_template("auth/login.html", next=next, email=email, error=str(e)), 400
    send_link(accounts.normal_email(email), token, next=next)
    return render_template("auth/sent.html", email=accounts.normal_email(email),
                           minutes=settings().auth.link_minutes)


@auth.route("/auth/link/<token>", methods=["GET", "POST"])
def link(token):
    """A sign-in link. Opening it only shows a button (mail scanners open
    links; they don't press buttons); pressing it signs in or approves
    the device."""
    if not accounts_enabled():
        return redirect(url_for("index"))
    conn = get_db()
    next = safe_next(request.values.get("next"))
    link = accounts.pending_link(conn, token)
    if request.method == "GET":
        if link is None:
            return render_template("auth/link.html", error=True), 410
        device = accounts.link_device(conn, link)
        return render_template("auth/link.html", error=False, email=link.email,
                               device=device.name if device else None, next=next)
    try:
        user, device = accounts.use_link(conn, token)
    except accounts.AccountError:
        return render_template("auth/link.html", error=True), 410
    if device is not None:
        return render_template("auth/approved.html", device=device, email=user.email)
    response = redirect(next)
    set_cookie(response, accounts.create_session(conn, user, settings().auth.session_days))
    return response


@auth.route("/auth/logout", methods=["POST"])
def logout():
    if accounts_enabled():
        accounts.end_session(get_db(), request.cookies.get(COOKIE))
    g.session_token = None
    response = redirect(url_for("auth.signed_out"))
    response.delete_cookie(COOKIE)
    return response


@auth.route("/auth/signed-out", methods=["GET"])
def signed_out():
    if current_user() is not None:
        return redirect(url_for("index"))
    return render_template("auth/signed_out.html")


@auth.route("/account", methods=["GET"])
def account():
    user = current_user()
    devices = accounts.find_tokens(get_db(), accounts.USER_TOKEN, user=user) \
        if accounts_enabled() else []
    return render_template("auth/account.html", user=user, devices=devices,
                           hostname=socket.gethostname())


@auth.route("/account/devices/<int:id>/revoke", methods=["POST"])
def revoke_device(id):
    if not accounts_enabled():
        abort(404)
    accounts.revoke_token(get_db(), id, user=current_user())
    return redirect(url_for("auth.account"))


def render_admin(new_token=None, error=None, status=200):
    conn = get_db()
    users = accounts.find_users(conn) if accounts_enabled() else []
    return render_template(
        "auth/admin.html",
        users=[(u, is_admin(u)) for u in users],
        admins=settings().auth.admins if accounts_enabled() else (),
        workers=accounts.find_tokens(conn, accounts.WORKER_TOKEN),
        new_token=new_token,
        error=error,
    ), status


@auth.route("/admin/", methods=["GET"])
@admin_required
def admin():
    return render_admin()


@auth.route("/admin/workers", methods=["POST"])
@admin_required
def create_worker_token():
    """A new worker token, shown once"""
    if not accounts_enabled():
        abort(404)
    name = request.form.get("name", "")
    try:
        secret = accounts.create_token(get_db(), accounts.WORKER_TOKEN, name,
                                       created_by=current_user())
    except accounts.AccountError as e:
        return render_admin(error=str(e), status=400)
    return render_admin(new_token={"name": name.strip(), "secret": secret})


@auth.route("/admin/workers/<int:id>/revoke", methods=["POST"])
@admin_required
def revoke_worker_token(id):
    if not accounts_enabled():
        abort(404)
    accounts.revoke_token(get_db(), id)
    return redirect(url_for("auth.admin"))
