%# The report's body, as reStructuredText (see rst_template.py: lines
%# starting % are Jinja statements, and {{ value }} is plain text).
%#
%# Things a document may want to show its own way are marked with plain
%# docutils constructs that carry a class, so every output can style them
%# and falls back to something sensible when it doesn't:
%#
%#   :pass:`pass`, :red:`red`, ...  a verdict: bold, and the LaTeX command
%#                                  \DUrole<verdict> if document.tex defines it
%#   .. container:: requirement     a requirement's own text: the LaTeX
%#                                  environment DUCLASSrequirement, if defined
%#
%# Values: report, rows, requirements, issues, untested, earlier, failures,
%# summary [(item, count)], versions, environments, runs, first_run,
%# last_run, exported, manifest_hash, verdicts.
% for verdict in verdicts
.. role:: {{ verdict | rst }}(strong)
% endfor

Identification
==============

.. list-table:: Report
   :header-rows: 1
   :widths: 25 75

   * - Item
     - Value
   * - Report
     - {{ report.id | literal }}
   * - Name
     - {{ report.name }}
   * - Workspace
     - {{ report.workspace }}
   * - Created
     - {{ report.created | stamp }}
   * - Runs
     - {{ runs | length }}, from {{ first_run | stamp or "-" }} to {{ last_run | stamp or "-" }}
   * - UUT versions
     - {{ versions | join(", ") }}
   * - Environments
     - {{ environments | join("; ") }}
   * - Exported
     - {{ exported | stamp }}
   * - Bundle
     - {{ ("report-%s.zip" % report.id) | literal }}
   * - Manifest SHA-256
     - {{ manifest_hash | literal }}

Summary
=======

The report covers {{ requirements | length | plural("requirement") }} with
{{ rows | length | plural("combination") }} of script, environment and variation.
Each combination is judged on its latest run; a requirement is green when every
combination linked to it passed, red when any failed, untested when no script
references it yet, and partial otherwise.

.. list-table:: Summary
   :header-rows: 1
   :widths: 70 30

   * - Item
     - Count
% for item, count in summary
   * - {{ item }}
     - {{ count }}
% endfor

Open issues
===========

% if not issues and not untested
None: the latest run of every combination passed.
% endif
% for requirement in untested
- {{ requirement.id | literal }}: untested, no script references it yet
% endfor
% for row in issues
- {{ row | combination | literal }}: {{ row.state | verdict }}{{ row | why }}
% endfor

Requirements
============

% if requirements
.. list-table:: Requirements
   :header-rows: 1
   :widths: 15 40 9 36

   * - Requirement
     - Text
     - Verdict
     - Covered by
% for r in requirements
   * - {{ r.id | literal }}
     - {{ r.text | requirement | indent(7) }}
     - {{ r.color | verdict }}
     -
% for c in r.cells
       | {{ c | combination }}: {{ c.state | verdict }}
% else
       *no tests yet*
% endfor
% endfor
% else
The report tracks no requirements.
% endif

Results
=======

The latest run of each combination of script, environment and variation;
earlier attempts are listed under Reruns. Run ids name the run's folder under
{{ ("report-%s/runs/" % report.id) | literal }}.

% if rows
.. list-table:: Results
   :header-rows: 1
   :widths: 27 43 19 11

   * - Combination
     - Run
     - Outcome
     - Duration
% for r in rows
   * - {{ r | combination }}
     - {{ r.latest.id | literal if r.latest else "" }}
     - {{ r.state | verdict }}{% if r.attempts > 1 %}, {{ r.attempts | plural("attempt") }}{% endif %}
     - {{ r.duration | seconds }}
% endfor
% else
None.
% endif
% if earlier

Reruns
------

Earlier attempts of each combination, newest first.

% for row in earlier
- {{ row | combination }}:

% for run in row.earlier
  - {{ run.id | literal }}: {{ run.outcome or "unfinished" }}
% endfor

% endfor
% endif
% if failures

Failures
--------
% for row in failures

{{ row | combination | heading("~") }}

Run {{ row.latest.id | literal }}, {{ row.state | verdict }}
{%- if row.failure.step %} at {{ row.failure.step }}{% endif %}.
% if row.failure.message

::

{{ row.failure.message | verbatim }}
% endif

Its events and attached files are in the report folder's
{{ ("runs/%s/" % row.latest.id) | literal }}.
% endfor
% endif

Bundle
======

This document describes the bundle report-{{ report.id }}.zip. Its folder
report-{{ report.id }} holds the report: ``report.json``, and for each run
``run.json``, the exact files it executed (``closure/``), every event it
recorded (``events.jsonl``) and the files attached to it (``files/``).
``template/`` is the template this document was rendered with.
``MANIFEST.sha256`` lists a SHA-256 for each of those files; its own SHA-256 is
{{ manifest_hash | literal }}.
