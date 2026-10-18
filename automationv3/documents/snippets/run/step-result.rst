%# .. step-result::  what came of one step: its state and duration, what its
%# block wrote of it (as_result_rst), the calls made in it, its output, why it
%# failed, and the files it attached.  result: a run.StepResult;  own: the
%# block's own rst, or None
.. container:: result {{ result.state | classes }}

   {% if result.duration is not none %}:duration:`{{ result.duration | duration }}` {% endif %}{{ result.state | verdict }}
% if own

{{ own | indent(3, true) }}
% endif
% if result.calls

   .. container:: calls

{{ result.calls | calls_rst | indent(6, true) }}
% endif
% if result.failure

   .. container:: failure

      ::

{{ result.failure.message | verbatim(9) }}
% for ex in result.failure.excerpts

      .. container:: excerpt

         {% if not loop.first %}called from {% endif %}{{ ex.where | literal }}

         ::

{{ ex | excerpt_rst | verbatim(12) }}
% endfor
% if result.failure.traceback

      .. container:: traceback collapsible

         Traceback

         ::

{{ result.failure.traceback | verbatim(12) }}
% endif
% endif
% if (result.stdout or result.stderr) and not (result.failure and result.stdout in result.failure.message)

   .. container:: output

      ::

{{ (result.stdout ~ ("\n" if result.stdout and result.stderr else "") ~ result.stderr) | verbatim(9) }}
% endif
% if result.attachments

   .. container:: attachments

      Files:{% for a in result.attachments %} {{ a.name | link(a.url, true) }}{% if not loop.last %},{% endif %}{% endfor %}

% endif
