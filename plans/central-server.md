# Central server, local client and accounts: implementation plan

Today one `server` process reads scripts from git worktrees on its own disk
and anyone who can reach it can do anything. This plan splits the system into
three modes and adds accounts.

## Decisions (from the design interview, 2026-10-23)

| Topic | Decision |
| --- | --- |
| Modes | **central** (shared server, accounts, git mirror), **client** (on each user's machine: CLI + local web UI against their worktrees), **single-user** (today's server: local worktrees, no login, one implicit admin user). Same code, switched by settings. |
| Script source | The central server mirrors the team's git remote; clients may also upload closures from their worktrees. |
| Reports vs scratch | Reports run only commits the server sees on the remote. Uploaded scripts and builds run only in scratch. |
| Mirror freshness | Webhook from the git host (GitHub or GitLab style), plus a fetch of the branch just before queuing a report. Every remote branch is a workspace. |
| Scratch location | Central workers by default; the client can also run on the user's machine. Local results stay local. |
| Builds | automation-v3 never stores builds: they live in a separate build repo with its own GC; UUT installers pull from it. UUT plugins gain `find_local_build(path)` and `upload_build(build)` hooks; the client's config names each UUT's build folder. The client pushes with the user's own git credentials. The UI notices a local build that isn't uploaded and offers "use last used" or "upload latest". |
| Sign-in | Passwordless magic link by email: single use, 15 minutes. Anyone at an allowed email domain gets an account on first sign-in. Every page needs sign-in. Sessions last 30 days, sliding. Mail goes through an SMTP relay; without one the link is logged. |
| Client auth | `automation-v3 login` asks for the email; the emailed link approves the device; the client stores a long-lived, revocable token. |
| Worker auth | Admins issue a token per worker; runs record which token's worker ran them. |
| Admins | An email list in the server settings. |
| Ownership | Reports have an owner and collaborators; only they (or an admin) change a report. Everyone can view everything. Scratch runs are owned by whoever ran them. |
| Default filter | Reports and Queue show what you own or collaborate on; Scratch shows your runs. One toggle shows everyone's. |
| Fairness | Scratch jobs go ahead of report jobs; reports stay FIFO. |
| Requirements in the client | Live API calls to the central server. |
| Requirement imports | Admins, in the UI or with `requirements import --server`; each import records who. |
| Scale | One team: under 50 users, under 20 workers. SQLite (WAL) and report folders on the server's disk. |

## Steps

Each step is one commit (or a few), with tests, keeping the whole suite
green. Steps marked **docs** update the documentation in the same commit.

1. **Plan.** This file.
2. **Server settings.** A TOML settings file (`server --settings PATH`):
   `base_url`, `[auth]` (allowed domains, admins, session and link
   lifetimes), `[smtp]`, `[git]` (remote, webhook secret). No `[auth]` means
   single-user mode. Requires Python 3.11 (tomllib).
3. **Accounts service.** `services/accounts.py`: users, single-use login
   links, sessions (sliding), device logins, user API tokens and worker
   tokens. Only token hashes are stored. `services/mail.py` sends links by
   SMTP, or logs them.
4. **Sign-in in the web app** (**docs**: `operating/accounts.rst`). Sign-in
   pages (the link's page has a button, so mail scanners that open links
   don't use them up), `g.user` on every request, everything behind sign-in
   in central mode, the user in the header, an Account page listing devices,
   and an Admin page listing users. Single-user mode signs everyone in as
   the local admin.
5. **Worker tokens** (**docs**: `operating/workers.rst`). Admins create and
   revoke them on the Admin page; workers send `Authorization: Bearer`
   (`token` in worker.json or `AUTOMATION_WORKER_TOKEN`); the job API checks
   them in central mode; runs record the token's name.
6. **Ownership and filters** (**docs**: `operating/reports.rst`,
   `operating/scratch.rst`). `owner` and `collaborators` in report.json,
   `owner` in scratch runs' run.json and on queued jobs. Changing a report
   needs owner, collaborator or admin. Reports, Queue and Scratch default
   to "mine", with an "Everyone" toggle. Collaborators are managed on the
   report's page.
7. **Scratch first.** Workers are offered scratch jobs before report jobs.
8. **Workspace sources (refactor).** Pages ask a workspace source for
   branches, files, checked-in files and edits, instead of calling
   `find_worktrees` themselves. `LocalWorktrees` is today's behaviour.
9. **Git mirror** (**docs**: `operating/deployment.rst`). `MirrorWorkspaces`
   keeps a `git clone --mirror` of `[git] remote` and shows each branch's
   tip (no edits: everything is checked in). `POST /hooks/git` (GitHub
   HMAC signature or GitLab token) fetches; queuing a report fetches its
   branch first. Additions record the commit they ran.
10. **Client API on the server.** `/api/...` with user tokens: device
    login (start, approve by link, poll), whoami, requirement lookup,
    environments and UUT versions, scratch upload (a closure's files) and
    run status.
11. **Client CLI** (**docs**: `operating/local-client.rst`). `login`,
    `logout` and `scratch SCRIPT...` (uploads from the worktree, waits and
    prints the outcome). Credentials live in
    `~/.config/automation-v3/credentials.json` (mode 600).
12. **Local web client.** `automation-v3 client`: the workspace pages on
    the user's worktrees, requirements from the central server, Run in
    scratch on central workers or on this machine (local results stay in
    the client's own folder), and Queue opening the central server's
    dialog for the branch.
13. **Local builds** (**docs**: `blocks/uuts-and-environments.rst`,
    `operating/local-client.rst`). The UUT hooks, client config of build
    folders, detection of builds that aren't uploaded, upload with the
    user's credentials, and "use last used". The sample `demo` UUT
    implements them against a folder standing in for the build repo.
14. **Requirement imports by admins** (**docs**:
    `operating/requirements.rst`). An upload form on the Imports page for
    admins, `requirements import --server URL`, and imports and link
    reviews record who made them.
15. **Wrap up.** README, the operating overview diagram, and a full test
    run.

## Out of scope for now

- SSO, passwords and a second factor.
- Postgres or object storage.
- Per-report privacy: everything stays visible to every signed-in user.
- Moving existing single-user data into a central server: existing reports
  have no owner, so only admins can change them.

## Status (2026-10-24)

Steps 1–15 are done, one commit each. The suite has 636 tests, all passing
except two that were already failing before this work (URL-encoding
assertions in `test_jobs.TestWorkerAgainstServer.test_requirements_page_lists_linked_scripts`
and `test_requirement_features.TestPages.test_a_spec_as_a_page`). A smoke
test with real processes worked end to end: a central server mirroring a
local remote, browser sign-in by the logged link, an admin-made worker token,
`login` by device link, `scratch` from a clone running on that worker, the
local `client` uploading to the server, and a signed GitHub-style webhook
fetching a new branch.

Changes to the plan along the way:

- Uploaded builds would have shown up in reports, because a plugin's
  `list_versions` includes them. UUTs gained `report_versions()` (default:
  every version), which report pages and plans use; scratch plans use every
  version.
- `Run again` on an uploaded scratch run reruns the same files on the
  server, since the worktree is on someone's machine.
- The CLI reference now copies the real `--help` text, with a test that
  keeps the two the same.

## Follow-ups

- Rate-limit sign-in emails (per address and per client IP). Today anyone
  can make the server email any allowed-domain address.
- The local `client` listens on 127.0.0.1 without its own sign-in, so other
  accounts on the same machine could use it as you. Fine on a personal
  workstation, not on a shared one.
- Report pages still show change buttons to people who can't use them (the
  server refuses with 403). Hide them.
- The local client has no offline cache of requirements; `:req:` shows bare
  ids when the server can't be reached.
- `datetime.utcnow()` deprecation warnings in services/jobs.py (older code).
