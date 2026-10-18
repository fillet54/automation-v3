%# .. table-results::  each row of a table block: its values and state, and
%# its steps with their results.  rows: [{name, values, state, message,
%# duration, steps: [(statement, result, own)]}]
% if duration is not none
.. container:: table-total

   {{ rows | length | plural("row") }} :duration:`{{ duration | duration }}`

% endif
% for row in rows
.. container:: table-row collapsible {{ row.state | classes }}

   **Row** {{ row.name }}{% if row["values"] %} · {{ row["values"] | values_text }}{% endif %}{% if row.duration is not none %} :duration:`{{ row.duration | duration }}`{% endif %} {{ row.state | verdict }}
% if row.message

   ::

{{ row.message | verbatim(6) }}
% endif
% for statement, result, own in row.steps

   .. container:: step

{{ statement.rst | rst | indent(6, true) }}

{{ context.render("run/step-result.rst", result=result, own=own) | indent(6, true) }}
% endfor

% endfor
