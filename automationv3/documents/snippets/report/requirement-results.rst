%# .. requirement-results::  each requirement's text, verdict and the
%# combinations covering it, grouped by subsystem.
%#    :group-by: subsystem (default) or none
%#    :subsystem: only this subsystem;  :color: only green, red, ...
% if not groups
The report tracks no requirements.
% endif
% for name, requirements in groups
% if name

.. rubric:: {{ name }}
% endif

.. list-table:: Requirements{% if name %}: {{ name }}{% endif %}
   :header-rows: 1
   :widths: 15 40 9 36

   * - Requirement
     - Text
     - Verdict
     - Covered by
% for r in requirements
   * - :anchor:`req-{{ r.id }}`\ {{ r.id | link(r.url) }}{% if r.changed %}

       :verdict:`text changed since`{% endif %}
     - {{ r.text | requirement | indent(7) }}
     - {{ r.color | verdict }}
     -
% for c in r.cells
       | {{ c | combination_name | link(c | run_url) }}: {{ c.state | verdict }}
% else
       *no tests yet*
% endfor
% endfor
% endfor
