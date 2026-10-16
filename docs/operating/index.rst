Operating
=========

.. rst-class:: lead

   Running the server and workers, queuing work into reports, and reading
   the results.

The pieces
----------

.. mermaid::
   :caption: The server keeps the queue and the results; workers next to the hardware pull jobs and send results back

   flowchart TB
     people([People, in a browser]):::ghost
     git([The scripts' git repository]):::ghost
     subgraph server [Server]
       web[Web app]
       api[Job API]:::accent
       queue[("Job queue<br/>sqlite")]
       workspace[("Workspace<br/>git checkout, read-only")]
       reports[("reports/<br/>run folders")]
     end
     subgraph lab [Lab PC]
       worker[Worker]:::accent
       sim[sim environment]
       bench[bench environment]
       uut[UUTs]
     end
     people --> web
     git -. checked out as .-> workspace
     web -- renders and lints --> workspace
     web -- queues --> queue
     web -- shows --> reports
     worker -- "checks in, polls, claims<br/>(connects out)" --> api
     worker -- "streams events, files<br/>and the outcome" --> api
     api --> queue
     api -- writes --> reports
     worker -- hosts --> sim
     worker -- hosts --> bench
     sim -- runs --> uut
     bench -- runs --> uut

The server
   Serves the web app and the job API. It reads scripts from the workspace,
   keeps the job queue in a sqlite database, and stores finished runs as
   files under the reports folder.

Workers
   Run next to the hardware, poll the server for jobs they can run, and
   stream each run's events and attached files back. A server can also run
   a worker in-process (``--local-worker``).

In this section
---------------

:doc:`workers`
   Configuring workers and environments, and how jobs are scheduled.

:doc:`reports`
   Creating reports, adding requirements and tests to them, and reading the
   rollup and runs.

:doc:`configuration-management`
   What a run records, identity, reruns and drift.

:doc:`scratch`
   Running scripts under development, outside any report.

Storage
-------

The database only holds the job queue and in-progress state. It is created,
or brought up to date, when the server starts.

Finished runs are plain files under ``--reports-path`` (default
``./reports``):

.. code-block:: text

   reports/
     <report uuid7>/
       report.json            name, UUT versions, scripts, tracked requirements, additions
       runs/
         <run uuid7>/
           run.json           outcome, environment, variation, versions, fingerprint, identity
           events.jsonl       every step, call and phase event, in order
           closure/           the exact files that ran
           files/             files blocks attached
     scratch/                 scratch runs (no report.json)

Being plain files, reports can be archived, copied or inspected with ordinary
tools.
