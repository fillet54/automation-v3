%# .. precondition-result::  the phases a Precondition ran: its check, its
%# heal if the check came out false, and the check again.  p: the
%# statement's precondition (name, heal_name, check_rst, heal_rst)
% if not phases
.. container:: precondition-parts

   **Check**

{{ p.check_rst | rst | indent(3, true) }}

.. step-result:: {{ statement_index }}
% else
% for phase in phases

.. container:: step phase

   **{% if phase.action == "heal" %}Heal{% if p.heal_name %}: {{ p.heal_name }}{% endif %}{% elif loop.first %}Check{% else %}Check again{% endif %}**

{{ (p.heal_rst if phase.action == "heal" else p.check_rst) | rst | indent(3, true) }}

   .. container:: result {{ phase.state | classes }}

      {% if phase.result and phase.result.duration is not none %}:duration:`{{ phase.result.duration | duration }}` {% endif %}{{ phase.state | verdict }}
% if phase.calls

      .. container:: calls

{{ phase.calls | calls_rst | indent(9, true) }}
% endif
% set failed = failure_of(phase.result) if phase.state != "false" or loop.last else None
% if failed

      .. container:: failure

         ::

{{ failed.message | verbatim(12) }}
% endif
% endfor
% endif
