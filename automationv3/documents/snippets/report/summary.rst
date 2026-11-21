%# .. report-summary::  the outcome in a sentence, and the requirements by verdict
% set requirements = data.requirements
{{ data | summary_text }}
% if requirements

.. list-table:: Requirements by verdict
   :header-rows: 1
   :widths: 70 30

   * - Verdict
     - Requirements
% for color in ["red", "partial", "untested", "green"]
   * - {{ color | verdict }}
     - {{ requirements | selectattr("color", "equalto", color) | list | length }}
% endfor

A requirement is green when the latest run of every script variation
covering it passed, red when any failed, partial when some haven't run or
aren't finished, and untested when no script covers it yet.
% endif
