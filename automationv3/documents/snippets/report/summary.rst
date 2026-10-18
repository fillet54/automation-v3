%# .. report-summary::  counts of requirements and combinations by state
% set requirements = data.requirements
% set rows = data.combinations
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
% if requirements
% for color in ["green", "red", "partial", "untested"]
   * - Requirements {{ color | verdict }}
     - {{ requirements | selectattr("color", "equalto", color) | list | length }}
% endfor
% endif
% for state in rows | states
   * - Combinations {{ state | verdict }}
     - {{ rows | selectattr("state", "equalto", state) | list | length }}
% endfor
