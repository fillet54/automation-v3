%# .. script-results::  each script once: its verdict (the worst of its
%# variations' latest runs) and how its variations came out
% set scripts = data.combinations | by_script
% if scripts
.. list-table:: Scripts
   :header-rows: 1
   :widths: 45 17 38

   * - Script
     - Verdict
     - Variations
% for g in scripts
   * - {{ g.script }}
     - {{ g.state | verdict }}
     - {{ g | variations }}
% endfor
% else
None.
% endif
