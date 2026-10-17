Requirements
============

.. rst-class:: lead

   Requirements come from DOORS as specs: a system spec, segment specs and
   software requirements specs, traced to each other and versioned by
   content. Automation keeps every version, so it can show what a spec said
   at any baseline, what changed since, and which tests that touches.

Specs and traces
----------------

A spec is a document: requirements, and the headings, prose, tables and
figures around them. Each has a key (``SRS-VM``), a level and the specs above
it:

.. mermaid::
   :caption: The demo's specs, and the way their requirements trace

   flowchart BT
     vm["SRS-VM<br/>Vehicle Manager SRS"] -- satisfies --> space["SEG-SPACE<br/>Space segment spec"]
     vmc["SRS-VMC<br/>Vehicle Management<br/>Computer SRS"] -- satisfies --> ground["SEG-GROUND<br/>Ground segment spec"]
     space -- satisfies --> sys["SYS<br/>System spec"]:::accent
     ground -- satisfies --> sys

A requirement traces up with ``:satisfies:``, naming the requirements above
it that it helps meet. The link is written on the child; automation works out
the other direction (what satisfies this?) and finds trace issues: a link to
an id that doesn't exist, or to a spec that isn't one of the spec's parents.

Ids are unique across all specs. Requirements carry attributes (verification
method, allocation, status), declared per spec; the ``subsystem`` attribute
groups them on the Requirements page and in reports.

How specs arrive is :doc:`requirements-export`: a folder from the DOORS
exporter, imported with ``automation-v3 requirements import``.

Trunk and baselines
-------------------

Each spec has a **trunk**, its current state in DOORS, exported as often as
daily, and **baselines**, frozen versions such as ``2.1``. A **baseline set**
(a release) pins one baseline of each spec, as DOORS baseline sets do.

Importing trunk compares it with the trunk before, requirement by
requirement, and logs what changed. Trunk only moves forward: an export
older than the trunk already imported is refused. Importing a baseline stores it once and
never again, and refuses different content under the same name. An import of
unchanged content changes nothing, so the exporter can run on a schedule and
the log only grows when DOORS did.

Versions are by content
-----------------------

A requirement's version is a hash of its content, in four parts, so history
can say *what* changed:

- **text**: the plain text, whitespace collapsed;
- **metadata**: its attributes, except those marked as volatile;
- **links**: its ``:satisfies:`` ids;
- **section**: the headings it's under.

Dates play no part: "recently changed" means changed in a recent import, and
a re-export that only reformats nothing doesn't show up.

History and differences
-----------------------

From those versions automation answers:

- **A requirement's history**: each import that changed it, and which parts,
  and the baselines it appears in.
- **What changed between two points**: two baselines, two baseline sets, a
  baseline and trunk, or two trunk imports; for a whole spec, a subsystem or
  everything. Requirements added, removed, and changed (and how).
- **What changed recently**: the trunk import log, newest first.

Changes reach tests
-------------------

When a requirement's text changes, everything below it may need another
look: the requirements that satisfy it, and the scripts that reference it
with ``:req:``. Both become **suspect** until someone reviews them; a
script's review is recorded for its workspace against the text it was
reviewed against, so it becomes suspect again only on the next change.

Each workspace verifies one context: trunk, or a baseline set. Its
requirement texts, coverage and suspects are those of that context. A run
records the version of each requirement it verified, so a report can tell a
pass against today's text from a pass against an older one.

Using them
----------

:doc:`../operating/requirements` covers importing from CI, the Requirements
pages, setting the context a workspace verifies, and reviewing suspects.
