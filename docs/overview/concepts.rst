Concepts
========

.. rst-class:: lead

   The vocabulary used throughout these docs and the web app.

.. code-block:: text

   requirement ◀── referenced by ── script ── loads ──▶ core.rst chain + imports
                                     │                   (together: the closure)
                                     │ declares
                                     ▼
                       environments × variations × UUT versions
                                     │ queued as
                                     ▼
                     job ── pulled by ──▶ worker ── hosts ──▶ environment ── runs ──▶ UUT
                                     │
                                     ▼
                         run (in a report) ── rolls up to ──▶ requirement status

Scripts and their closure
-------------------------

Script
   An ``.rst`` document containing at least one ``rvt`` block. Each form in an
   ``rvt`` block is a step, a definition or a directive. See
   :doc:`../scripts/first-script`.

``core.rst``
   A folder's shared definitions. A script loads the ``core.rst`` of every
   folder from the workspace root down to its own, then those of folders it
   imports with ``(import FOLDER)``.

Closure
   The script plus every file it loaded. The closure is hashed, and copied
   into the run, so a result can always be traced to the exact text that ran.

Workspace
   A git checkout (or worktree) the app reads scripts from. The app never
   writes to it.

What a script runs against
--------------------------

UUT
   A unit under test, e.g. a controller's software. A UUT type is a Python
   plugin that lists its versions, installs one into an environment, starts
   it, and gives scripts a **handle** to talk to it. Scripts declare what
   they test with ``(uut :demo)``.

Environment
   Where a script runs: a simulator, a bench, a rig. Hosted by workers.
   Scripts declare where they can run with ``(environments :sim :bench)``.

Variation
   One way of running a script, binding the same symbols to different values,
   e.g. ``normal`` and ``limp-home`` braking modes. A script with three
   variations that runs in two environments has six **combinations**.

Precondition
   The state a script needs before its steps, with an optional **heal** that
   establishes it. Workers use preconditions to schedule work on warm hardware.

Running
-------

Job
   One combination of a script queued to run: script, environment, variation
   and UUT versions.

Worker
   A process next to the hardware that hosts one or more environments, pulls
   jobs it can run, executes them and streams results back.

Run
   The record of one executed job: its outcome (:status:`passed`,
   :status:`failed`, :status:`blocked` or :status:`error`), the events of
   each step, files blocks attached, and the closure.

Report
   A named collection of runs against chosen UUT versions, that grows as
   requirements and tests are added to it. Its **rollup** shows each tracked
   requirement as green, red or partial.

Identity
   The hash of a run's closure, variation values, UUT versions and the
   environment's fingerprint. Two runs with the same identity ran the same
   test on the same configuration.

Who does what
-------------

Script writer
   Writes scripts in rst and edn, using definitions and BuildingBlocks.
   Start at :doc:`../scripts/index`.

Block developer
   Writes BuildingBlocks, UUTs and environments in Python.
   Start at :doc:`../blocks/index`.

Operator
   Runs the server and workers, queues reports and reads their results.
   Start at :doc:`../operating/index`.
