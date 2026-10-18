%# .. failures::  where and why each failing combination failed
% set failures = data.combinations | selectattr("failure") | list
% if not failures
No combination failed.
% endif
% for row in failures

.. rubric:: {{ row.name }}

Run {{ row.latest.id | link(row | run_url, true) }}, {{ row.state | verdict }}
{%- if row.failure.step %} at {{ row.failure.step }}{% endif %}.
% if row.failure.message

::

{{ row.failure.message | verbatim }}
% endif

Its events and attached files are in the report folder's
{{ ("runs/%s/" % row.latest.id) | literal }}.
% endfor
