%# .. open-issues::  each requirement that isn't green and the scripts
%# keeping it so; then each failure once: where, why, and what it fails
% set open = data.requirements | open_requirements
% set failing = data.combinations | selectattr("failure") | list
% set covered = data.requirements | map(attribute="cells") | sum(start=[]) | list
% set loose = data.combinations | rejectattr("state", "equalto", "pass") | rejectattr("failure") | list
% if not open and not failing and not loose
None: every requirement passed.
% endif
% if open

.. list-table:: Open requirements
   :header-rows: 1
   :widths: 20 14 66

   * - Requirement
     - Verdict
     - Why
% for r in open
   * - {{ r.id | link(r.url) }}
     - {{ r.color | verdict }}
     -
% for g in r.cells | by_script | rejectattr("state", "equalto", "pass")
% for c in g.cells | rejectattr("state", "equalto", "pass")
       | {{ g.script }}{% if c.label %} ({{ c.label }}){% endif %}: {{ c | issue }}
% endfor
% else
       No script covers it yet.
% endfor
% endfor
% endif
% for row in failing
% if loop.first

.. rubric:: Failures
% endif

**{{ row | combination_name }}** {{ row.state | verdict }}
{%- if row.failure.step %} at {{ row.failure.step }}{% endif %},
run {{ row.latest.id | link(row | run_url, true) }}.
% set fails = row | covers(data.requirements)
% if fails
It fails {{ fails | map(attribute="id") | join(", ") }}.
% endif
% if row.failure.message

::

{{ row.failure.message | verbatim }}
% endif
% endfor
% set loose = loose | reject("in", covered) | list
% if loose

.. rubric:: Other scripts that didn't pass

% for row in loose
- {{ row | combination_name }}: {{ row | issue }}
% endfor
% endif
