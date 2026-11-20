Deployment
==========

.. rst-class:: lead

   One program, three ways to run it: a central server the team shares, a
   client on each person's machine, or a single-user server for working
   alone.

The three modes
---------------

.. mermaid::
   :caption: A central server mirrors the team's repository; clients and workers connect to it

   flowchart LR
     subgraph desk [Each person's machine]
       worktree[("Git worktrees")]
       client["Client<br/>CLI and local web UI"]:::accent
       builds[("Local builds")]
     end
     git([The team's git remote]):::ghost
     buildrepo([The build repository]):::ghost
     subgraph central [Central server]
       web["Web app and APIs"]:::accent
       mirror[("Mirror of the remote")]
       db[("Accounts, queue<br/>sqlite")]
       reports[("reports/")]
     end
     subgraph lab [Lab]
       worker[Workers]:::accent
     end
     worktree -- push --> git
     git -- "webhook, fetch" --> mirror
     client -- reads --> worktree
     client -- "scratch uploads,<br/>requirements" --> web
     client -- "pushes, with your<br/>own credentials" --> buildrepo
     builds --> client
     worker -- "worker token" --> web
     worker -- "installers pull" --> buildrepo
     web --> mirror
     web --> db
     web --> reports

**Central server**
   The team's server: ``automation-v3 server --settings server.toml``, with
   ``[auth]`` and ``[git]`` in the settings. Everyone signs in (see
   :doc:`accounts`). Scripts come from a mirror of the team's git remote.
   Reports run only what has been pushed, and record the commit they ran.
   Workers in the lab connect to it with worker tokens (see :doc:`workers`).

**Client**
   On each person's machine (see :doc:`local-client`). It reads scripts in
   their own git worktrees, checks them as they're written, and runs them in
   scratch, on the central server's workers or on the machine itself. It
   uploads local builds of a UUT to the build repository. Requirements come
   from the central server.

**Single-user server**
   ``automation-v3 server --workspace-path SCRIPTS`` with no settings.
   ``SCRIPTS`` is the scripts folder in a git worktree (its top, or a folder
   below it); each worktree of that repository is a workspace, with its
   scripts in the same folder,
   there's no sign-in and nobody owns anything. It suits a laptop, a lab with
   one person, and the demo.

Settings
--------

A central server's settings are a TOML file:

.. code-block:: toml

   base_url = "https://automation.example.com"

   [auth]
   allowed_domains = ["example.com"]
   admins = ["lead@example.com"]

   [smtp]
   host = "mail.example.com"
   sender = "automation@example.com"

   [git]
   remote = "git@git.example.com:team/scripts.git"
   webhook_secret = "a long random string"   # or AUTOMATION_WEBHOOK_SECRET
   scripts = "rvts"                          # the scripts folder; default: the top
   # mirror_path = "mirror.git"              # default; relative to the database's folder

:doc:`accounts` describes ``[auth]`` and ``[smtp]``. An unknown setting is an
error at startup, so a misspelling doesn't quietly do nothing.

The mirror
----------

With ``[git]``, the server keeps a ``git clone --mirror`` of ``remote`` next to
its database, and every branch of the remote that has the ``scripts`` folder
is a workspace, shown at its latest commit. The server's own account needs read access to the remote
(for example a deploy key). It never pushes.

Nothing is edited on the server, so there are no in-work files: what you
see is what was pushed. To run something that isn't pushed yet, use
scratch from the client.

The mirror is kept current two ways:

**The webhook**
   Point the git host's push webhook at ``https://SERVER/hooks/git`` with
   ``webhook_secret`` as its secret. GitHub and Gitea sign the body
   (``X-Hub-Signature-256`` or ``X-Gitea-Signature``); GitLab sends the
   secret as ``X-Gitlab-Token``. Anything else is refused, and so is every
   webhook while no secret is set.

**Before queuing**
   Queuing a report fetches first, so "I just pushed" works even if a webhook
   was missed. Each addition and run records the commit it ran.

The server clones or fetches when it starts, and won't start if it can't.

Running it
----------

- Put it behind a reverse proxy that terminates HTTPS, and set ``base_url``
  to the ``https://`` address. Emailed links use it, and session cookies are
  then only sent over HTTPS.
- One process serves one team (tens of users, a few dozen workers): sqlite
  in WAL mode and report folders on local disk are enough. Back up the
  database file and the reports folder together.
- Workers connect out to the server, so lab machines need no inbound access.
