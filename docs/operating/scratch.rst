The scratch space
=================

.. rst-class:: lead

   Run scripts while you write them, without adding anything to a report.

**Scratch** in the navigation is for scripts under development. Pick a
workspace, scripts, an environment and UUT versions, and run. Every variation
runs.

How it differs from a report
----------------------------

- Scratch runs use the workspace's files **as they are on disk**,
  uncommitted edits included.
- They never appear in a report or a rollup.
- There is one scratch space, shared by everyone.

Each run has **Run again**, which re-reads the script's current files, so
the loop is: edit, Run again, read the result. **Clear finished runs**
deletes the finished ones.

When the script works
---------------------

A scratch run can't be promoted into a report, because it may have run text
that was never committed. Commit the script, then use **Queue in a report…**
on the scratch run's page to run it properly.

From the command line
---------------------

``automation-v3 run`` is the offline equivalent: it runs scripts on your
machine with no server, prints each step and writes a report folder locally.
See :doc:`../reference/cli`.
