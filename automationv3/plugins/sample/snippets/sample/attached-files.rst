%# .. attached-files::  every file the report's runs attached, by run (the sample plugin's)
% if not runs
No run attached a file.
% else
.. container:: attached-files

% for run, files in runs
   - {{ run.script }}, run {{ run.id | link(data.links.run(data.id, run.id), true) }}:
     {% for name in files %}{{ name | link(data.links.file(data.id, run.id, name), true) }}{% if not loop.last %}, {% endif %}{% endfor %}

% endfor
% endif
