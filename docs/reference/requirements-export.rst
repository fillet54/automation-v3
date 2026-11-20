Requirements export format
==========================

.. rst-class:: lead

   What the DOORS exporter writes and automation imports: a folder holding a
   manifest and one Sphinx source tree per spec. This page is the contract
   between the two; the exporter is a separate application. Without DOORS, a
   spec can be imported from a CSV or a list instead.

An export is a folder. Each run of the exporter writes a new one; automation
imports it with ``automation-v3 requirements import FOLDER``.

.. code-block:: text

   export-2026-10-17/
     manifest.json
     MSN/                  one folder per spec in the manifest
       index.rst
       landing.rst
       images/fig-1.png
     LM/
       index.rst
     LGC/
       index.rst
       programs.rst
       propellant.rst

An export may hold any number of specs, and the same spec more than once (its
trunk and a new baseline, say), or only baseline sets over baselines imported
before. Specs not in the manifest are not touched by
the import: a folder exporting only ``LGC`` says nothing about ``MSN``.

The manifest
------------

``manifest.json`` describes the export and each spec in it:

.. code-block:: json

   {
     "format": 1,
     "exporter": {"name": "doors-export", "version": "0.3.0"},
     "exported_at": "2026-10-17T02:00:00Z",
     "specs": [
       {
         "key": "LGC",
         "title": "Guidance Computer Software Requirements (Luminary)",
         "level": "software",
         "parents": ["LM"],
         "root": "LGC",
         "doors": {"module": "/Lunar Module/Software/LGC",
                   "id_source": "Absolute Number"},
         "attributes": {
           "subsystem": {"type": "string"},
           "verification": {"type": "enum",
                            "values": ["Test", "Analysis", "Inspection",
                                       "Demonstration"]},
           "allocation": {"type": "list"},
           "last-modified-by": {"type": "string", "hashed": false}
         }
       },
       {
         "key": "LGC",
         "baseline": "2.1",
         "root": "LGC@2.1",
         "...": "the same fields as above"
       }
     ],
     "baseline_sets": [
       {"name": "Release 2",
        "specs": {"MSN": "1.0", "LM": "1.2", "LGC": "2.1"}}
     ]
   }

``format``
   The version of this contract: ``1``. Automation refuses formats it doesn't
   know.

``exported_at``
   When the exporter read DOORS: ISO 8601 with a time zone
   (``2026-10-17T02:00:00Z``). Needed whenever the export holds a trunk. It
   orders trunk, which only moves forward: an export older than the trunk
   already imported for a spec is refused, so re-running an old pipeline
   can't roll trunk back. What *changed* is still decided by content, never
   by dates.
``exporter``
   Informational: the exporter's name and version.

``specs``
   One entry per spec in the export:

   ``key``
      The spec's short, stable name (``MSN``, ``LM``, ``LGC``).
      Letters, digits, ``-``, ``_`` and ``.``.
   ``title``
      Its name for people.
   ``level``
      Where it sits: ``system``, ``segment`` or ``software``.
   ``parents``
      The keys of the specs its requirements may trace up to. A system spec
      has none.
   ``root``
      The folder, relative to the manifest, holding the spec's Sphinx source,
      with ``index.rst`` at its top.
   ``baseline``
      The DOORS baseline this is, such as ``"2.1"``. Absent for trunk: the
      module's current, unbaselined state.
   ``doors``
      Where it came from: the module's path and which DOORS column gave the
      requirement ids (``id_source``). Informational.
   ``attributes``
      The spec's attribute schema (below).

``baseline_sets``
   DOORS baseline sets: a name, and the baseline of each spec it pins. Each
   pinned baseline must be in this export or imported before. Optional.

The spec's documents
--------------------

A spec is a Sphinx source tree, without ``conf.py``: automation supplies the
configuration, the ``requirement`` directive and the theme when it renders
the spec, so every spec looks like the rest of the site. ``index.rst`` holds
the spec's title and a ``toctree`` of its chapters; everything DOORS holds
that isn't a requirement (headings, prose, tables, figures) is written as
ordinary rst, and images go in the tree and are referenced relatively.

Write headings without their DOORS numbers ("Power", not "3.2 Power"):
Sphinx numbers them, and a number that shifts whenever a section is
inserted above would make every requirement below look moved.

Each requirement is a ``requirement`` directive:

.. code-block:: rst

   .. requirement:: LM-EPS-002
      :satisfies: MSN-004
      :subsystem: EPS
      :verification: Test
      :allocation: EPS, CWEA
      :last-modified-by: jdoe

      The electrical power system shall light the caution and warning
      lights for the bus:

      - the BATTERY caution on a battery fault or a bus below 26.5 V;
      - the WARNING light on a bus below 24 V.

The argument
   The requirement's id. The spec's ``doors.id_source`` says where the
   exporter took it from: the object's absolute number (with the module's
   prefix) or a column of its own. Ids are unique across every spec; an
   import that would give two specs the same id fails.

``:satisfies:``
   The ids of the parent requirements this one traces up to, comma
   separated. Links are written on the child only, like DOORS out-links;
   automation works out the other direction. A link need not resolve: one
   whose target is missing, or in a spec that isn't one of ``parents``, is
   shown as a trace issue rather than failing the import.

Every other option
   An attribute, named as in the spec's schema. Option names are lower case,
   with ``-`` for spaces (``Last Modified By`` is ``last-modified-by``).

The content
   The requirement's text, in rst: lists, emphasis, notes and tables are all
   fine. It must not be empty.

Attribute schemas
-----------------

Each spec lists the attributes its requirements may carry. An option not in
the schema, or a value its type doesn't allow, fails the import, so a typo
can't quietly become a new attribute.

``"type"``
   ``string`` (any one-line value), ``enum`` (one of ``"values"``) or
   ``list`` (comma-separated values; their order doesn't matter).
``"hashed"``
   ``false`` for attributes that change without the requirement changing:
   DOORS's Last Modified On and By, Object Number, Created Thru. They are
   kept and shown, but a change to them is not a new version. Default
   ``true``.

An attribute named ``subsystem`` groups requirements on the Requirements
page and in reports. Map whichever DOORS column holds it (Allocation, CSCI,
Subsystem) to ``subsystem``.

What makes a change
-------------------

Automation decides what changed by hashing content, so the exporter must be
deterministic: the same DOORS content exported twice must give the same
requirements. It need not give identical bytes. Each requirement is hashed in
four parts:

text
   The plain text of the content, with whitespace collapsed. Markup
   (emphasis, line wrapping, list bullets) doesn't count, so improving the
   RTF conversion doesn't make every requirement look changed; wording does.
metadata
   The hashed attributes and their values.
links
   The ``:satisfies:`` ids, as a set.
section
   The titles of the sections the requirement is in, from its chapter down.
   A requirement moved to another section has moved; one reordered within
   its section has not.

The whole source tree of each spec is kept too, so any version can be shown
exactly as it was.

.. _flat-requirements:

A CSV or a list
---------------

Without DOORS, or before its exporter is ready, a spec can come from a
spreadsheet or a text file instead. Each file is one spec; importing it names
the spec (``--spec SRS`` on the command line, or the Spec field on the
Imports page), and may give its title, baseline, level (software by default)
and parents. It is read into the same form as an export, so everything works
the same: re-importing an edited file is a new trunk, with its history,
changes and suspects, and ``--baseline 1.0`` freezes a version.

A **spreadsheet** (``.csv``, ``.tsv`` with tabs, or an Excel workbook,
``.xlsx``) has a header row, then a row per requirement. Each column has a
role: the id, the text, the ids it satisfies, its section, an attribute, or
ignored. On the command line the roles are guessed from the headers; the
Imports page guesses too, then lets you change them (see
:doc:`../operating/requirements`). A workbook's sheet is ``--sheet NAME``, by
default the first with anything on it.

.. code-block:: text

   id,text,satisfies,section,subsystem,verification
   SRS-001,The LGC shall light PRPLNT LOW below 6% of the load.,LM-PRP-003,Propellant,PRP,Test
   SRS-002,The LGC shall show the propellant remaining on N93.,,Propellant,PRP,Test
   SRS-003,The LGC shall keep mission elapsed time.,LM-GNC-001,Time,TIM,Analysis

``id`` and ``text``
   Needed. Guessed from headers like *ID*, *Req ID*, *Object Identifier*,
   and *Text*, *Requirement*, *Object Text*. An id has no spaces or commas,
   and is unique in the file; a text
   may span lines (quoted, as spreadsheets save it), and a blank line in it
   starts a new paragraph.
``satisfies``
   Optional (*Parent*, *Parent Requirements*, *Traces to*): the ids it
   traces up to, separated by commas, semicolons or line breaks. They should
   be in the specs given as ``parents``, or show as trace issues.
``section``
   Optional: a heading to file it under, as a spec document's headings do.
   Moving a requirement to another section is a change; reordering rows is
   not.
Every other column
   An attribute, kept as text, named after its header in lower case with
   ``-`` between words (*Verification Method* is ``verification-method``). A
   ``subsystem`` attribute groups requirements as it does for DOORS.

A **list** (``.txt``) has one requirement per line: its id (a colon after it
is fine), then spaces or a tab, then its text. Blank lines, and lines starting with
``#``, are skipped.

.. code-block:: text

   # The guidance SRS, until DOORS
   SRS-001  The LGC shall light PRPLNT LOW below 6% of the load.
   SRS-002: The LGC shall show the propellant remaining on N93.

The text is plain: characters reStructuredText would read as markup, like
``*`` or a leading ``-``, are kept as written. Save files as UTF-8 (Excel's
*CSV UTF-8*). A file with a problem (a missing id or text, an id twice) is
refused whole, with every problem and its line listed.

Each requirement needs an id that stays the same from one import to the
next: it is how history, ``:req:`` references and reports find it. A list of
bare texts can't be imported, as an id made up from a line's position or its
words would change whenever the file did.

Checklist for the exporter
--------------------------

- One folder per run, with ``manifest.json`` at its top, ``"format": 1``,
  and ``exported_at`` the time DOORS was read, in UTC.
- One entry per spec and version: trunk with no ``baseline``, each DOORS
  baseline with its name. A baseline, once imported, can't change: exporting
  ``LGC 2.1`` again with different content is an error.
- Every spec a Sphinx tree under its ``root``, ``index.rst`` at the top, no
  ``conf.py``.
- Headings without their DOORS numbers.
- One ``requirement`` directive per requirement object, with its id, its
  ``:satisfies:`` links and its attributes as options.
- Every attribute in the spec's schema; volatile ones ``"hashed": false``.
- Deterministic output: nothing that changes between runs of unchanged
  content (no timestamps in the documents).
- DOORS baseline sets in ``baseline_sets``.
