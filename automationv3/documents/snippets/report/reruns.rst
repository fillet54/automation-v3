%# .. reruns::  earlier attempts of each combination, newest first
% set earlier = data.combinations | selectattr("earlier") | list
% if not earlier
No combination was run more than once.
% endif
% for row in earlier
- {{ row.name }}:

% for run in row.earlier
  - {{ run.id | link(data.links.run(data.id, run.id), true) }}: {{ (run.outcome or "unfinished") | verdict }}
% endfor

% endfor
