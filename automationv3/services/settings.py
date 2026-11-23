"""Server settings: what makes a server central

A TOML file, given to `server --settings PATH`::

    base_url = "https://automation.example.com"   # links in emails

    [auth]                         # sign-in; without it: single-user mode
    allowed_domains = ["example.com"]
    admins = ["lead@example.com"]
    session_days = 30              # sliding: renewed while used
    link_minutes = 15              # how long a sign-in link works

    [smtp]                         # without it, sign-in links are logged
    host = "mail.example.com"
    port = 25
    starttls = false
    username = ""                  # optional
    password = ""                  # optional; or AUTOMATION_SMTP_PASSWORD
    sender = "automation@example.com"

    [git]                          # mirror a remote instead of local worktrees
    remote = "git@git.example.com:team/scripts.git"
    webhook_secret = "..."         # or AUTOMATION_WEBHOOK_SECRET
    mirror_path = "mirror.git"     # relative to the database's folder
    scripts = "rvts"               # the scripts folder in the repository
                                   # (default: its top)

With no file, a server is single-user: local worktrees, no sign-in.
"""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class SettingsError(ValueError):
    pass


@dataclass(frozen=True)
class Auth:
    allowed_domains: tuple = ()
    admins: tuple = ()
    session_days: int = 30
    link_minutes: int = 15

    def allows(self, email):
        """True if `email` is at one of the allowed domains"""
        domain = email.rpartition("@")[2].lower()
        return any(domain == d.lower().lstrip("@") for d in self.allowed_domains)

    def is_admin(self, email):
        return email.lower() in {a.lower() for a in self.admins}


@dataclass(frozen=True)
class Smtp:
    host: str
    port: int = 25
    starttls: bool = False
    username: str = ""
    password: str = ""
    sender: str = "automation@localhost"


@dataclass(frozen=True)
class Git:
    remote: str
    webhook_secret: str = ""
    mirror_path: str = "mirror.git"
    scripts: str = ""  # the scripts folder, a path in the repository ("": its top)


@dataclass(frozen=True)
class Settings:
    base_url: str = ""
    auth: Auth = None
    smtp: Smtp = None
    git: Git = None
    extra: dict = field(default_factory=dict, compare=False)

    @property
    def central(self):
        """Accounts and sign-in are on"""
        return self.auth is not None


def _section(data, name, cls, required=()):
    raw = data.get(name)
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise SettingsError(f"[{name}] should be a table")
    known = set(cls.__dataclass_fields__)
    unknown = set(raw) - known
    if unknown:
        raise SettingsError(f"[{name}] has unknown settings: {', '.join(sorted(unknown))}")
    for key in required:
        if not raw.get(key):
            raise SettingsError(f"[{name}] needs {key}")
    values = {k: tuple(v) if isinstance(v, list) else v for k, v in raw.items()}
    return cls(**values)


def parse(data, env=None):
    """Settings from a parsed TOML document. Raises SettingsError."""
    env = os.environ if env is None else env
    unknown = set(data) - {"base_url", "auth", "smtp", "git"}
    if unknown:
        raise SettingsError(f"Unknown settings: {', '.join(sorted(unknown))}")
    auth = _section(data, "auth", Auth)
    if auth is not None:
        if not auth.allowed_domains:
            raise SettingsError("[auth] needs allowed_domains: who may sign in")
        if auth.session_days <= 0 or auth.link_minutes <= 0:
            raise SettingsError("[auth] session_days and link_minutes should be positive")
    smtp = _section(data, "smtp", Smtp, required=("host",))
    if smtp is not None and not smtp.password and env.get("AUTOMATION_SMTP_PASSWORD"):
        smtp = Smtp(**{**smtp.__dict__, "password": env["AUTOMATION_SMTP_PASSWORD"]})
    git = _section(data, "git", Git, required=("remote",))
    if git is not None and not git.webhook_secret and env.get("AUTOMATION_WEBHOOK_SECRET"):
        git = Git(**{**git.__dict__, "webhook_secret": env["AUTOMATION_WEBHOOK_SECRET"]})
    return Settings(base_url=str(data.get("base_url", "")).rstrip("/"),
                    auth=auth, smtp=smtp, git=git)


def load(path=None, env=None):
    """The settings in the TOML file at `path`; single-user settings if
    `path` is None. Raises SettingsError."""
    if path is None:
        return Settings()
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as e:
        raise SettingsError(f"Can't read {path}: {e}") from None
    except tomllib.TOMLDecodeError as e:
        raise SettingsError(f"{path} isn't valid TOML: {e}") from None
    return parse(data, env)
