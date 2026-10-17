The scratch space
=================

.. rst-class:: lead

   Run scripts while you write them, without adding anything to a report.

In work and checked in
----------------------

The workspace shows each branch's files as they are on disk. When a script,
or a ``core.rst`` or import it loads, has edits that aren't committed, its
page says so and offers three views:

**In work**
   The files as they are on disk, edits included.
**Checked in**
   The files as committed on the branch.
**Changes**
   What the edits change, file by file.

Reports run only what is checked in: **Queue…** builds from the committed
files, says which scripts have edits it is leaving out, and won't take a
script that isn't committed at all. Scratch is where in-work files run.

Running in scratch
------------------

**Run in scratch** on a script's page runs it outside any report: the
variation picked on the page (or every variation), in the environment picked
beside the button (or every environment it supports), with the newest UUT
versions. It runs the files you're looking at: in work, or as checked in.

**Scratch** in the navigation lists the runs, newest first, with the files
each used and a link back to its script. **Run again** re-reads the same
files as they are now (in work or checked in, as before), so the loop is:
edit, Run again, read the result. **Clear finished runs** deletes the
finished ones.

How it differs from a report
----------------------------

- Scratch runs may use files that were never committed.
- They never appear in a report or a rollup.
- There is one scratch space, shared by everyone.

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
