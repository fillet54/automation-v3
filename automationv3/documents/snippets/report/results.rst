%# .. results::  the latest run of each combination.
%#    :script: only scripts matching this pattern;  :state: only pass, fail, ...
% if rows
.. list-table:: Results
   :header-rows: 1
   :widths: 27 43 19 11

   * - Combination
     - Run
     - Outcome
     - Duration
% for r in rows
   * - {{ r.name }}
     - {{ (r.latest.id if r.latest else "") | link(r | run_url, true) }}
     - {{ r.state | verdict }}{% if r.attempts > 1 %}, {{ r.attempts | plural("attempt") }}{% endif %}

     - {{ r.duration | seconds }}
% endfor
% else
None.
% endif
