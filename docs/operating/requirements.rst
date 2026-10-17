Requirements in practice
========================

.. rst-class:: lead

   Importing specs from DOORS on a schedule, reading them and what changed,
   and keeping scripts honest when a requirement moves under them.

How specs get in
----------------

The DOORS exporter writes an export folder (see
:doc:`../reference/requirements-export`); ``automation-v3 requirements
import`` reads it into the server's database. Run both from a scheduled CI
job, on a runner that can reach DOORS and the server's database:

.. code-block:: yaml

   # .gitlab-ci.yml
   import-requirements:
     tags: [automation-server]     # a shell runner on the server's host
     rules:
       - if: $CI_PIPELINE_SOURCE == "schedule"
     script:
       - doors-export --out "export-$CI_PIPELINE_ID"
       - automation-v3 requirements import "export-$CI_PIPELINE_ID"
           --dbpath /srv/automation/automationv3.db
     artifacts:
       paths: ["export-$CI_PIPELINE_ID/"]
       expire_in: 90 days

The import is safe to run as often as you like:

- **Unchanged content changes nothing.** The import is logged as having
  looked, and the log of changes only grows when DOORS did.
- **Trunk only moves forward.** An export older than the trunk already
  imported (by its ``exported_at``) is refused, so a re-run of an old
  pipeline can't roll trunk back. Re-running the *same* export is fine.
- **A baseline never changes.** Exporting a baseline again with different
  content fails the job, which is what you want to hear about.
- **All or nothing.** An export with any problem (an attribute not in its
  schema, an id in two specs, a baseline set naming a baseline that doesn't
  exist) is refused whole, and the job fails with every problem listed.

Keeping each pipeline's export folder as an artifact means any import can be
looked at, or run again, later.

The Requirements pages
----------------------

**Requirements**
   The requirements in a context (trunk, a baseline set or one spec's
   baseline), by spec or subsystem, with the scripts that test each. Pick
   requirements to queue their scripts. A spec can be read as the document it
   is, with its headings, prose and figures, and its requirements linked.

**A requirement**
   Its text and attributes, what it satisfies and what satisfies it, the
   scripts that test it, and its history: each trunk import that changed it,
   word by word, and the baselines it is in.

**Changes**
   What was added, removed and changed between any two contexts, for
   everything, one spec or one subsystem: Release 1 against trunk, or trunk
   as of one import against trunk as of another.

**Suspects**
   Links that may need another look (below).

**Imports**
   Each import, newest first, and what it changed in trunk.

Which requirements a workspace verifies
---------------------------------------

A workspace verifies trunk unless it says otherwise. A release branch names
the baseline set it verifies in ``automation.json`` at its root:

.. code-block:: json

   {"requirements": "set:Release 1"}

Its Requirements pages, suspects and new reports then use that context, and
the setting travels with the branch. Any page can still show another context
for a moment with the picker in its side column.

Suspect links
-------------

When a requirement's text changes, whatever was written against the old text
may be wrong. Two kinds of link become **suspect**:

- a script's ``:req:`` reference, when the requirement's text in the
  workspace's context changed since the script was last reviewed;
- a requirement's ``:satisfies:`` link, when its parent's text changed in
  trunk since the link was last reviewed.

A link counts as reviewed against the text it first meets, so only later
changes make it suspect, and only changes to the *text*: a new attribute
value or a reformatted export doesn't. The Suspects page shows each one with
what changed since its review; fix the script or requirement if it needs it,
then **Mark reviewed**.

What a report records
---------------------

A report verifies requirements in its workspace's context, and records it.
For each requirement it tracks, it keeps the text and the version (the spec
and a hash of the text) it took on, and each run keeps the version of every
requirement its script covers. When a requirement's text changes after the
report took it on, the report's runs page says so beside it: a pass against
the old text is still a pass against the old text.
