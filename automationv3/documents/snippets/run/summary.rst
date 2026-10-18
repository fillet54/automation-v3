%# .. run-summary::  what a run was: its outcome, where it ran, on what, and when
:Outcome: {{ (run.outcome or "unfinished") | verdict }}
:Run: {{ run.id | literal }}
:Script: {{ run.script | literal }}
% if run.environment
:Environment: {{ run.environment }}
% endif
% if run.variation
:Variation: {{ run.variation.name }}
% endif
% if run.uut_versions
:UUT versions: {{ run.uut_versions | uut_list }}
% endif
% if run.started
:Ran: {{ run.started | stamp }} to {{ run.ended | stamp or "-" }}
% endif
% if run.worker
:Worker: {{ run.worker | literal }}
% endif
