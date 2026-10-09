=================
Example test set
=================
Every script either works or fails on purpose, with the reason in its
documentation. Together they test every BRA and FUE requirement; the
other VMC subsystems are left without scripts on purpose.

The VM folder tests the Vehicle Manager, the flight software of a
satellite platform, against its requirements in
``test/data/requirements/vehicle_manager.rst`` (written for this project,
in rst). The tests are written as flows to review: most of their steps
are ``(TBD "...")`` placeholders, so every run comes out incomplete.
Their first steps are real: each checks the test's table of expected
values against the requirement, written once in ``VM/core.rst``.

================  =================================  =========================
Script            Shows                              Expected outcome
================  =================================  =========================
BRA/tc_bra_00001  core.rst chain, heal, Verify       pass
BRA/tc_bra_00002  a failing step form, nested calls  fail (on purpose)
BRA/tc_bra_00003  UUT version selection              pass on 1.1.0, fail 1.0.0
BRA/tc_bra_00004  variations, rvt-variant, titles    pass
BRA/tc_bra_00005  environments, try-ok?, quietly     pass in sim and bench
BRA/tc_bra_00006  a precondition that cannot heal    blocked (on purpose)
BRA/tc_bra_00007  a lint error (late precondition)   refuses to queue
BRA/tc_bra_00008  definitions section, config table  pass
FUE/tc_fue_00001  folder core.rst                    pass
FUE/tc_fue_00002  variations                         pass
FUE/tc_fue_00003  UUT handle: faults                 pass
FUE/tc_fue_00004  imports                            pass
VM/*/tc_*         Vehicle Manager, as TBD flows      incomplete
================  =================================  =========================
