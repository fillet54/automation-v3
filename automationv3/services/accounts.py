"""Accounts: users, passwordless sign-in, sessions and API tokens

Sign-in is by email. Someone gives their address; if it is at an allowed
domain they get a single-use link, which signs a browser in (a session)
or approves a device (a client's `login`, which then gets an API token).
A user exists from their first sign-in.

Secrets (link tokens, session tokens, device codes, API tokens) are
handed out once and only their sha256 is stored.

Times are UTC ISO strings; functions take `now` so tests can move it.
"""

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

USER_TOKEN, WORKER_TOKEN = "user", "worker"
TOKEN_PREFIX = {USER_TOKEN: "av3u_", WORKER_TOKEN: "av3w_"}

# A session or token is written back at most this often when used
TOUCH_EVERY = timedelta(minutes=10)

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AccountError(ValueError):
    pass


@dataclass(frozen=True)
class User:
    id: int
    email: str
    created_at: str = None
    last_seen_at: str = None

    @property
    def name(self):
        """What to call them: the part of the address before the @"""
        return self.email.partition("@")[0]


@dataclass(frozen=True)
class Token:
    id: int
    kind: str
    name: str
    user: User = None  # who a user token acts as
    created_at: str = None
    last_used_at: str = None
    revoked_at: str = None
    created_by: str = None  # email


def utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(when):
    return when.astimezone(timezone.utc).isoformat()


def parse(text):
    return datetime.fromisoformat(text)


def digest(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


def normal_email(email):
    """The address, trimmed and lower-cased. Raises AccountError if it
    doesn't look like one."""
    email = (email or "").strip().lower()
    if not EMAIL.match(email):
        raise AccountError(f"{email or 'That'} isn't an email address")
    return email


def check_allowed(auth, email):
    email = normal_email(email)
    if not auth.allows(email):
        raise AccountError(f"{email} can't sign in here: use your "
                           f"{' or '.join('@' + d for d in auth.allowed_domains)} address")
    return email


# Users


def _user(row):
    return User(row["id"], row["email"], row["created_at"], row["last_seen_at"]) \
        if row else None


def get_user(conn, id):
    return _user(conn.execute("SELECT * FROM users WHERE id = ?", (id,)).fetchone())


def find_user(conn, email):
    return _user(conn.execute("SELECT * FROM users WHERE email = ?",
                              (email.strip().lower(),)).fetchone())


def ensure_user(conn, email, now=None):
    """The user with `email`, created if they are new"""
    email = normal_email(email)
    with conn:
        conn.execute("INSERT INTO users(email, created_at) VALUES (?, ?) "
                     "ON CONFLICT(email) DO NOTHING", (email, iso(now or utcnow())))
    return find_user(conn, email)


def find_users(conn):
    """Every user, by email"""
    return [_user(row) for row in conn.execute("SELECT * FROM users ORDER BY email")]


def seen(conn, user, now):
    if user.last_seen_at is None or parse(user.last_seen_at) < now - TOUCH_EVERY:
        with conn:
            conn.execute("UPDATE users SET last_seen_at = ? WHERE id = ?",
                         (iso(now), user.id))


# Sign-in links


def create_link(conn, email, minutes, device_code_hash=None, now=None):
    """A new single-use link token for `email`. Each one is also when
    what has expired is forgotten (see forget_expired)."""
    now = now or utcnow()
    forget_expired(conn, now)
    token = secrets.token_urlsafe(32)
    with conn:
        conn.execute(
            "INSERT INTO login_links(token_hash, email, created_at, expires_at, "
            "device_code_hash) VALUES (?, ?, ?, ?, ?)",
            (digest(token), normal_email(email), iso(now),
             iso(now + timedelta(minutes=minutes)), device_code_hash))
    return token


def request_sign_in(conn, auth, email, now=None):
    """A sign-in link token for a browser. Raises AccountError if the
    address may not sign in."""
    return create_link(conn, check_allowed(auth, email), auth.link_minutes, now=now)


def pending_link(conn, token, now=None):
    """The link's row if it can still be used, else None"""
    now = now or utcnow()
    row = conn.execute("SELECT * FROM login_links WHERE token_hash = ?",
                       (digest(token or ""),)).fetchone()
    if row is None or row["used_at"] or parse(row["expires_at"]) <= now:
        return None
    return row


def link_device(conn, row):
    """The device login a link approves (its row), or None"""
    if not row["device_code_hash"]:
        return None
    return conn.execute("SELECT * FROM device_logins WHERE code_hash = ?",
                        (row["device_code_hash"],)).fetchone()


def use_link(conn, token, now=None):
    """Use a link once. Returns (user, device name or None). Raises
    AccountError if it is unknown, used or expired."""
    now = now or utcnow()
    row = pending_link(conn, token, now)
    if row is None:
        raise AccountError("That sign-in link has expired or was already used: "
                           "ask for a new one")
    with conn:
        used = conn.execute("UPDATE login_links SET used_at = ? "
                            "WHERE token_hash = ? AND used_at IS NULL",
                            (iso(now), row["token_hash"])).rowcount
    if not used:  # someone else used it in between
        raise AccountError("That sign-in link was already used: ask for a new one")
    user = ensure_user(conn, row["email"], now)
    device = link_device(conn, row)
    if device is not None:
        with conn:
            conn.execute("UPDATE device_logins SET approved_user = ? WHERE code_hash = ?",
                         (user.id, device["code_hash"]))
        return user, device["name"]
    return user, None


# Sessions


def create_session(conn, user, days, now=None):
    """A session token signing `user` in for `days`"""
    now = now or utcnow()
    token = secrets.token_urlsafe(32)
    with conn:
        conn.execute("INSERT INTO sessions(token_hash, user_id, created_at, expires_at) "
                     "VALUES (?, ?, ?, ?)",
                     (digest(token), user.id, iso(now), iso(now + timedelta(days=days))))
    return token


def session_user(conn, token, days, now=None):
    """The user a session token signs in, or None. Using a session moves
    its expiry to `days` from now."""
    if not token:
        return None
    now = now or utcnow()
    row = conn.execute("SELECT * FROM sessions WHERE token_hash = ?",
                       (digest(token),)).fetchone()
    if row is None:
        return None
    expires = parse(row["expires_at"])
    if expires <= now:
        end_session(conn, token)
        return None
    if expires < now + timedelta(days=days) - TOUCH_EVERY:
        with conn:
            conn.execute("UPDATE sessions SET expires_at = ? WHERE token_hash = ?",
                         (iso(now + timedelta(days=days)), row["token_hash"]))
    user = get_user(conn, row["user_id"])
    seen(conn, user, now)
    return user


def end_session(conn, token):
    with conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (digest(token or ""),))


# Device logins (automation-v3 login)


def start_device_login(conn, auth, email, name, now=None):
    """Begin signing a client in. Returns (device code, link token): the
    client keeps the code and polls with it; the link goes by email."""
    now = now or utcnow()
    email = check_allowed(auth, email)
    name = (name or "").strip()[:100] or "a client"
    code = secrets.token_urlsafe(32)
    with conn:
        conn.execute("INSERT INTO device_logins(code_hash, email, name, created_at, "
                     "expires_at) VALUES (?, ?, ?, ?, ?)",
                     (digest(code), email, name, iso(now),
                      iso(now + timedelta(minutes=auth.link_minutes))))
    link = create_link(conn, email, auth.link_minutes, digest(code), now)
    return code, link


def poll_device_login(conn, code, now=None):
    """The API token for an approved device login, handed out once; None
    while it waits for its link. Raises AccountError when it expired or
    was already collected."""
    now = now or utcnow()
    row = conn.execute("SELECT * FROM device_logins WHERE code_hash = ?",
                       (digest(code or ""),)).fetchone()
    if row is None or row["issued_at"]:
        raise AccountError("Unknown sign-in: start again")
    if row["approved_user"] is None:
        if parse(row["expires_at"]) <= now:
            raise AccountError("The sign-in link expired: start again")
        return None
    with conn:
        issued = conn.execute("UPDATE device_logins SET issued_at = ? "
                              "WHERE code_hash = ? AND issued_at IS NULL",
                              (iso(now), row["code_hash"])).rowcount
    if not issued:
        raise AccountError("Unknown sign-in: start again")
    user = get_user(conn, row["approved_user"])
    return create_token(conn, USER_TOKEN, row["name"], user=user, now=now)


# API tokens


def create_token(conn, kind, name, user=None, created_by=None, now=None):
    """A new API token: a user's (a client device) or a worker's"""
    if kind not in TOKEN_PREFIX:
        raise ValueError(f"No token kind {kind}")
    if kind == USER_TOKEN and user is None:
        raise ValueError("A user token needs its user")
    name = (name or "").strip()
    if not name:
        raise AccountError("A token needs a name")
    token = TOKEN_PREFIX[kind] + secrets.token_urlsafe(32)
    with conn:
        conn.execute(
            "INSERT INTO api_tokens(token_hash, kind, name, user_id, created_by, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (digest(token), kind, name, user.id if user else None,
             created_by.id if created_by else None, iso(now or utcnow())))
    return token


def _token(conn, row):
    creator = get_user(conn, row["created_by"]) if row["created_by"] else None
    return Token(row["id"], row["kind"], row["name"],
                 get_user(conn, row["user_id"]) if row["user_id"] else None,
                 row["created_at"], row["last_used_at"], row["revoked_at"],
                 creator.email if creator else None)


def token_for(conn, secret, now=None):
    """The live (unrevoked) Token a secret is, or None"""
    if not secret:
        return None
    now = now or utcnow()
    row = conn.execute("SELECT * FROM api_tokens WHERE token_hash = ? AND revoked_at IS NULL",
                       (digest(secret),)).fetchone()
    if row is None:
        return None
    if row["last_used_at"] is None or parse(row["last_used_at"]) < now - TOUCH_EVERY:
        with conn:
            conn.execute("UPDATE api_tokens SET last_used_at = ? WHERE id = ?",
                         (iso(now), row["id"]))
    token = _token(conn, row)
    if token.user is not None:
        seen(conn, token.user, now)
    return token


def find_tokens(conn, kind, user=None, revoked=False):
    """Tokens of `kind` (only `user`'s, if given), newest first"""
    query = "SELECT * FROM api_tokens WHERE kind = ?"
    params = [kind]
    if user is not None:
        query += " AND user_id = ?"
        params.append(user.id)
    if not revoked:
        query += " AND revoked_at IS NULL"
    query += " ORDER BY id DESC"
    return [_token(conn, row) for row in conn.execute(query, params)]


def revoke_token(conn, id, user=None, now=None):
    """Revoke a token (only if it is `user`'s, when given). Returns True
    if it was live."""
    query = "UPDATE api_tokens SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL"
    params = [iso(now or utcnow()), id]
    if user is not None:
        query += " AND user_id = ?"
        params.append(user.id)
    with conn:
        return conn.execute(query, params).rowcount == 1


def forget_expired(conn, now=None):
    """Delete expired links, sessions and device logins"""
    now = iso(now or utcnow())
    with conn:
        conn.execute("DELETE FROM login_links WHERE expires_at <= ?", (now,))
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        conn.execute("DELETE FROM device_logins WHERE expires_at <= ? "
                     "AND (approved_user IS NULL OR issued_at IS NOT NULL)", (now,))
