Reports
=======

.. rst-class:: lead

   A report is a named body of evidence: runs against chosen UUT versions,
   rolled up to the requirements they verify. It grows as you add to it.

Creating a report
-----------------

**Reports → New report** asks for:

- a **name**, e.g. "Brakes, release 1.1 candidate";
- the **workspace** its scripts come from;
- one **version per UUT type**, the default for everything added.

The report starts empty.

Adding to a report
------------------

**Add requirements…**
   Adds every script linked to the chosen requirements, and **tracks** the
   requirements: they appear in the report's rollup.

**Add a test…**
   Adds one script, without tracking its requirements.

Each addition queues every combination of the script's environments and
variations (you can narrow both), using the report's UUT versions unless you
override them for that addition. If additions use different versions, the
report shows the mix.

Combinations that have already passed in the report are left out of an
addition, unless you tick **Run again what already passed**.

The Requirements page and the script view also have an **Add to** / **Queue
in** report picker. Leaving it blank creates a new report in one step, named
after what it covers.

The rollup
----------

Each tracked requirement is judged on the latest run of every combination of
every script linked to it:

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - State
     - When
   * - green
     - the latest run of every linked combination passed
   * - red
     - the latest run of any linked combination failed
   * - partial
     - anything else: not run yet, queued, running, blocked or error

Linked scripts that weren't added, and variations that were left out, count
as not run, so a requirement is only green when its whole coverage passed.

Reading a run
-------------

A run page shows the script as it ran, for the variation it ran:

- under the breadcrumbs, the variation, the outcome and the **Rerun**
  button;
- **Details**: the environment, UUT versions, mode, timings and
  configuration facts (see :doc:`configuration-management`);
- each step with its badge, its duration to the millisecond, and, when
  expanded, its output, nested block calls and attached files;
- preconditions collapsed to their description and badge, expanding to each
  phase.

Earlier runs of the same combination are kept and listed with the latest.
