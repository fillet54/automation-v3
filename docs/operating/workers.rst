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

.. mermaid::
   :caption: Warm-first: run what fits the environment as it is, and only start fresh when nothing does

   flowchart TB
     idle([Poll for pending jobs]) --> next{{"Another pending job<br/>it can run?"}}
     next -- yes --> installed{{"Probe it: its UUT versions<br/>already installed?"}}
     installed -- yes --> holds{{"Its preconditions<br/>hold, or heal?"}}
     installed -- no --> release[Release it to the queue]
     holds -- no --> release
     release --> next
     holds -- yes --> run[Run its steps]:::success
     next -- none left --> any{{Any pending job at all?}}
     any -- no --> idle
     any -- yes --> force["Force mode, the oldest:<br/>install if needed, start fresh"]:::warning
     force --> holds2{{"Its preconditions<br/>hold, or heal?"}}
     holds2 -- yes --> run
     holds2 -- no --> blocked[blocked]:::warning

UUTs are never torn down between jobs. The run page records the mode a run
ran in, and for each UUT whether it was installed or kept.

Talking to the server
---------------------

A worker only ever makes requests to the server, under ``/runner``:

.. mermaid::
   :caption: One job, from the worker's poll to its outcome in the report

   sequenceDiagram
     participant W as Worker
     participant S as Server
     participant R as reports/
     W->>S: POST /workers: check in, with environments and fingerprints
     loop every 2 s while idle
       W->>S: GET /jobs?worker_url=…
       S-->>W: pending jobs it can run, oldest first
     end
     W->>S: POST /jobs/ID/claim
     S-->>W: the job, with its closure
     W->>S: POST /jobs/ID/start
     alt a probe that doesn't fit
       W->>S: POST /jobs/ID/release
       Note over S: pending again, for any worker
     else it runs
       loop as the script runs
         W->>S: POST /jobs/ID/events, /files
         S->>R: events.jsonl, files/
       end
       W->>S: POST /jobs/ID/complete: outcome, installed, fingerprint, mode
       S->>R: run.json
       Note over S: the job leaves the queue
     end

A worker checks in again every minute. One that hasn't for five minutes is
taken as lost, and the jobs it held end in :status:`error`.

.. mermaid::
   :caption: A job in the queue. Its outcome is kept in the run's run.json, not in the queue

   stateDiagram-v2
     [*] --> pending: queued
     pending --> claimed: claim
     claimed --> running: start
     claimed --> pending: release
     running --> pending: release
     running --> finished: complete
     claimed --> finished: worker lost
     running --> finished: worker lost
     finished --> [*]

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
