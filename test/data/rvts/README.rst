=================
Example test set
=================
Every script either works or fails on purpose, with the reason in its
documentation. Together they test every BRA and FUE requirement; the
other subsystems are left without scripts on purpose.

================  ====================================  ========================
Script            Shows                                 Expected outcome
================  ====================================  ========================
BRA/tc_bra_00001  core.rvt chain, precondition + heal   pass
BRA/tc_bra_00002  a failing step                        fail (on purpose)
BRA/tc_bra_00003  UUT version selection                 pass on 1.1.0, fail 1.0.0
BRA/tc_bra_00004  variations table, StartDemo heal      pass
BRA/tc_bra_00005  multiple environments                 pass in sim and bench
BRA/tc_bra_00006  a precondition that cannot heal       blocked (on purpose)
BRA/tc_bra_00007  a lint error                          refuses to queue
BRA/tc_bra_00008  a block rendering its config table    pass
FUE/tc_fue_00001  folder core.rvt                       pass
FUE/tc_fue_00002  variations                            pass
FUE/tc_fue_00003  UUT handle: faults                    pass
FUE/tc_fue_00004  imports                               pass
================  ====================================  ========================
