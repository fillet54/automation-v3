=================
Example test set
=================
Every script either works or fails on purpose, with the reason in its
documentation. Together they test every BRA and FUE requirement; the
other subsystems are left without scripts on purpose.

================  =================================  =========================
Script            Shows                              Expected outcome
================  =================================  =========================
BRA/tc_bra_00001  core.rst chain, heal, Verify       pass
BRA/tc_bra_00002  a failing defblock, nested calls   fail (on purpose)
BRA/tc_bra_00003  UUT version selection              pass on 1.1.0, fail 1.0.0
BRA/tc_bra_00004  variations table, StartDemo heal   pass
BRA/tc_bra_00005  environments, passes?, quietly     pass in sim and bench
BRA/tc_bra_00006  a precondition that cannot heal    blocked (on purpose)
BRA/tc_bra_00007  a lint error (late precondition)   refuses to queue
BRA/tc_bra_00008  definitions section, config table  pass
FUE/tc_fue_00001  folder core.rst                    pass
FUE/tc_fue_00002  variations                         pass
FUE/tc_fue_00003  UUT handle: faults                 pass
FUE/tc_fue_00004  imports                            pass
================  =================================  =========================
