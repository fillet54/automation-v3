Workers
=======

.. rst-class:: lead

   A worker hosts environments, pulls jobs it can run, and reports back. Put
   one on every machine that can reach a simulator or bench.

Starting a worker
-----------------

.. code-block:: bash

   automation-v3 worker --central-server automation.example:8080 --config worker.json

The worker connects out to the server, so lab machines need no inbound
access. By default it also serves a small status page on ``--port``; add
``--no-http`` to run without it.

The config file
---------------

The config names the environments the worker hosts, with each environment's
parameters:

.. code-block:: json

   {
     "environments": {
       "sim": {"workdir": "/var/lib/automation/sim"},
       "bench": {}
     }
   }

Each name must match an environment plugin's ``name``; its parameters are
passed to the plugin's constructor. See
:doc:`../blocks/uuts-and-environments`.

What a worker offers
--------------------

When it checks in, a worker tells the server which environments it hosts and
each one's fingerprint. The server only hands it jobs for those environments,
and a pinned rerun only to a worker whose fingerprint matches.

Scheduling
----------

Workers schedule **warm-first**:

1. Every pending job the worker can run is **probed** against the
   environment as it is: if its UUT versions are already installed, its
   preconditions are checked and healed.
2. The first job whose preconditions hold runs. Others are released back to
   the queue untouched.
3. If none does, the oldest runs in **force mode**: UUT versions are
   installed if needed and started fresh, then the job's preconditions run.
   A precondition that still fails makes the run :status:`blocked`.

UUTs are never torn down between jobs. The run page records the mode a run
ran in, and for each UUT whether it was installed or kept.

Outcomes
--------

:status:`passed`
   Every step passed.

:status:`failed`
   A step failed; the rest didn't run.

:status:`blocked`
   A precondition couldn't be established, so the test didn't run.

:status:`error`
   Something outside the script went wrong: an install failed, the worker
   raised. The run page shows the traceback.

Running the server with a worker
--------------------------------

For a single machine:

.. code-block:: bash

   automation-v3 server --workspace-path ./scripts --local-worker --config worker.json

The in-process worker takes jobs straight from the server's database. Other
workers can still connect.
