%# .. requirement-results::  each requirement's text, verdict and the
%# scripts covering it (with how they came out, when not every variation
%# passed), grouped by subsystem.
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
   :widths: 15 47 10 28

   * - Requirement
     - Text
     - Verdict
     - Scripts
% for r in requirements
   * - :anchor:`req-{{ r.id }}`\ {{ r.id | link(r.url) }}{% if r.changed %}

       :verdict:`text changed since`{% endif %}
     - {{ r.text | requirement | indent(7) }}
     - {{ r.color | verdict }}
     -
% for g in r.cells | by_script
       | {{ g.script }}{% if g.state != "pass" %}: {{ g | tally }}{% endif %}
% else
       *no tests yet*
% endfor
% endfor
% endfor
