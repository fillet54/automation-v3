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

Reading a report
----------------

A report's pages share a navigation column on the left:

**Overview**
   The summary, each subsystem's state, every open issue (a combination
   whose latest run didn't pass) with why, and the report's document.

**Runs**
   Every tracked requirement, grouped by its subsystem: its text and state,
   and a row per script, environment and variation with the outcome,
   attempts and duration. A row that didn't pass says why underneath: the
   step that failed and its message, steps still to be written, or not run.

   In the navigation, Runs opens into a tree of subsystems, their
   requirements, and the tests run for each, by their titles. Scripts added
   on their own, without a requirement, are under **Other tests**. Each entry
   has a dot for how it stands:

   .. list-table::
      :widths: 20 80

      * - green
        - passed
      * - red
        - failed, or ended in an error
      * - amber
        - partial: incomplete, steps to be written, blocked
      * - hollow
        - not run yet
      * - pulsing
        - running

   A subsystem or requirement also shows how many of its entries have
   issues. Branches with issues start open; **Issues only** hides the rest.
   The navigation remembers what you open and close.

   Clicking a subsystem shows only its requirements; a requirement also
   scrolls to it, and a test to its rows. The address follows, e.g.
   ``/reports/<id>/runs?subsystem=EPS#req-VM-EPS-002``, so it can be shared,
   and back and forward work.

**Values touched**
   The values the latest runs read, set or fixed through connectors, grouped
   by connector (e.g. ``vm.eps``), with every fixed value listed first.

**History**
   What was added to the report, every combination's latest and earlier
   runs, and scripts that couldn't be added.

While runs are in progress, the page and its navigation refresh every few
seconds. Rename a report with the pencil beside its title; its name is the
title of its exported document too.

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

Issuing a report
----------------

When a report has to be handed over as a formal document, export it. An
export **freezes** the report and writes ``report-<id>.zip``:

``report.pdf``
   The document: a title page, contents, a signature page, the applicable
   and reference documents, then the report itself (identification, a
   summary, open issues, every requirement with its text and verdict, and
   one line per combination). Only failures are spelled out, with the step
   that failed and why.

``report-<id>/``
   The report folder as it is kept: ``report.json``, and for each run the
   files it executed, every event it recorded and the files attached to it.

``template/``
   The document template the PDF was made with.

``MANIFEST.sha256``
   A SHA-256 for every file in the two folders above. The PDF prints the
   manifest's own SHA-256, on its title page and under Identification, so
   anyone can check the bundle is the one the document describes.

``report.rst`` and ``report.tex``
   The generated body and the whole document, to rebuild the PDF.

Before exporting, fill in the report's **Document** (on the Overview,
**Edit…**): its number, revision and author, who signs for each role
on the signature page, and its applicable and reference documents, one per
line as ``NUMBER | REVISION | TITLE``. Requirement texts are copied into the
report when requirements are added, so the PDF quotes what was tested
against. The document's title is the report's name.

**Freeze & export** needs every run to have finished. A frozen report takes
no more runs: its add buttons and **Rerun** are gone, and the report can't
be picked as a target. Its **Download** button gets the bundle. If a problem
turns up, **Reopen** it, fix what's wrong, and export again; only whether a
report is frozen is kept, not a history of freezes, so the manifest's SHA-256
is what tells two exports apart.

The same works without the server, on a report folder:

.. code-block:: console

   $ automation-v3 report edit reports/<id> --title "Brakes qualification" \
         --number TR-0042 --revision A --author "J. Smith" \
         --sign "Approved by=J. Doe" --applicable "SRS-1 | C | Requirements"
   $ automation-v3 report export reports/<id> --out issued/
   $ automation-v3 report reopen reports/<id>

Making the PDF needs a TeX distribution with ``latexmk`` (e.g. TeX Live).

The document template
~~~~~~~~~~~~~~~~~~~~~

A workspace keeps its template in a ``report/`` folder beside its ``rvts/``
folder; without one, a built-in placeholder template (a made-up company) is
used. Start from the built-in one, in
``automationv3/services/reports/template/``:

``template.json``
   The company name, the marking printed in every footer, the document type
   on the title page, and the signature page's roles.

``document.tex``
   The LaTeX document, as a Jinja template written with ``((( value )))``
   and ``((* statement *))`` so it doesn't clash with LaTeX's braces. It
   lays out the title page, headers and footers, signature page and
   documents table, and places the report's body.

``logo.pdf``, and any other file ``document.tex`` includes.
