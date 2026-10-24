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

Trying a script from the command line
-------------------------------------

.. code-block:: console

   $ cd ~/work/scripts/rvts
   $ automation-v3 scratch BRA/tc_bra_00004.rst
   Queued BRA/tc_bra_00004.rst (sim): https://automation.example.com/reports/scratch/runs/0193...

   BRA/tc_bra_00004.rst (sim), scratch mode
     ok   step 1
     FAIL step 2
     ...
     fail     BRA/tc_bra_00004.rst (sim)

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
