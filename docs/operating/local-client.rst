The local client
================

.. rst-class:: lead

   Write scripts in your own git worktrees and try them as you go, on the
   central server's benches or on your own machine, before anything is
   pushed.

Signing in
----------

.. code-block:: console

   $ automation-v3 login --server https://automation.example.com
   Your work email: ann@example.com
   We emailed ann@example.com a link. Open it and approve ann-laptop (it works for 15 minutes).
   Signed in to https://automation.example.com as ann@example.com

Open the link and press **Approve**. The client keeps a token for this machine
in ``~/.config/automation-v3/credentials.json``, which only you can read
(``$AUTOMATION_CONFIG_HOME`` or ``$XDG_CONFIG_HOME`` move it). The token acts
as you until you sign out or remove the device on your Account page (see
:doc:`accounts`).

``automation-v3 whoami`` says who this machine is signed in as.
``automation-v3 logout`` signs it out and revokes its token. Commands talk to
the server you last signed in to unless you name another with ``--server``.

The local web UI
----------------

.. code-block:: console

   $ automation-v3 client --workspace-path ~/work/scripts
      Signed in to https://automation.example.com as ann@example.com
      Client started: http://localhost:8080/

``client`` serves the workspace pages for your own clone and its worktrees, on
this machine only (it listens on 127.0.0.1). Scripts are rendered and checked
as you save them, with in-work edits marked just as on a single-user server.

What belongs to the team stays on the central server:

- **Requirements**, **Queue**, **Reports** and **Workers** in the header open
  the central server's pages.
- ``:req:`` references show the central server's text for the requirements
  your workspace verifies (its ``automation.json``). They're looked up live
  and kept for a minute.
- **Run in scratch** uploads the script's files, edits included, to the
  central server's scratch space and opens the run there. Start the client
  with ``--config worker.json`` and you can pick **on this machine** instead.
  The run then happens in the client's own worker, with the environments
  that config hosts, and its results stay in the client's folder
  (``~/.local/share/automation-v3/client``, or ``--data-path``). The client's
  **Scratch** page lists those runs.
- **Queue on the central server…** opens the central server's queue dialog
  for your branch. Reports run what was pushed, so push first.

On the central server, **Run again** on an uploaded run runs the same files
again, since the worktree they came from is on someone else's machine.
Upload again from the client to run your latest edits.

Local builds
------------

To run a scratch test on a build you've just made, tell the client where each
UUT's builds land on your machine, in ``client.json`` next to your
credentials:

.. code-block:: json

   {"builds": {"lm": "~/work/luminary/build"}}

For each UUT a script uses, **Run in scratch** then offers a version:

- **upload your local build**, when the newest build in that folder isn't in
  the build repository yet. A **New local build** badge marks it. Choosing it
  pushes the build to the build repository, using your own credentials (the
  UUT's plugin does the pushing; the central server never handles builds),
  and runs on it.
- the build repository's versions, newest first, with your uploaded build
  marked **your local build**, and the one you used last marked
  **last used**.

The default is your local build once it's uploaded, then whatever you used
last, then the newest version. Uploaded builds are cleaned up by the build
repository's own rules, and they're for scratch only: reports offer and
accept only the versions the UUT's plugin releases (its ``report_versions``,
see :doc:`../blocks/uuts-and-environments`).

From the command line, ``automation-v3 builds`` lists your local builds and
whether each is uploaded, and ``automation-v3 scratch SCRIPT --uut lm=local``
uses yours, uploading it first if needed.

Trying a script from the command line
-------------------------------------

.. code-block:: console

   $ cd ~/work/scripts/rvts
   $ automation-v3 scratch ALM/tc_alm_003.rst --env sim --variation extended --uut lm=LUM131
   Queued ALM/tc_alm_003.rst (sim, extended): https://automation.example.com/reports/scratch/runs/0193...

   ALM/tc_alm_003.rst (sim, extended), scratch mode
     ok   step 1: (lm-ready-for? mission :low-gate :manual)
     FAIL step 2: N93 against the loaded propellant
     ...
     fail     ALM/tc_alm_003.rst (sim, extended)

``scratch`` reads the script, and every ``core.rst`` and import it loads, from
your worktree as they are on disk, uncommitted edits included. It checks them
first and stops on any error. Then it uploads them to the central server's
scratch space, where they run on its workers. It prints each step as it runs
and exits non-zero unless every run passed.

``--env`` and ``--variation`` (both repeatable) narrow what runs, and
``--uut NAME=VERSION`` picks UUT versions (the newest by default).
``--no-wait`` queues the runs and prints their links without waiting.

Uploaded files only ever run in scratch. Each upload is recorded as
**uploaded**, with the branch your worktree has checked out and the machine
that sent it, and never counts toward a report. To put a script in a report,
push it, then queue it on the central server, which runs what was pushed (see
:doc:`deployment`).

To run on your own machine instead, with no server at all, use
``automation-v3 run`` (see :doc:`scratch`). Its results stay on your machine.
