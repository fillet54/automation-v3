%# .. open-issues::  untested requirements, and combinations that didn't pass
% set untested = data.requirements | selectattr("color", "equalto", "untested") | list
% set issues = data.combinations | rejectattr("state", "equalto", "pass") | list
% if not issues and not untested
None: the latest run of every combination passed.
% endif
% for requirement in untested
- {{ requirement.id | link(requirement.url) }}: untested, no script references it yet
% endfor
% for row in issues
- {{ row.name | link(row | run_url) }}: {{ row.state | verdict }}{{ row | why }}
% endfor
