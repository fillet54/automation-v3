===================================
The Apollo lunar module example set
===================================
Tests of the Apollo lunar module's powered descent and its guidance
computer's software, against the requirements in ``doors/specs`` (the
``MSN`` mission, ``LM`` lunar module and ``LGC`` software
specifications). They run against the simulated lunar module, the ``lm``
UUT, in the ``sim`` environment (stepped) and the ``lms`` environment
(the mission simulator, in paced real time).

Every script either works or fails on purpose, with the reason in its
documentation.

Versions and variations
-----------------------
The **version** under test is the guidance computer's software, a
Luminary rope:

- ``LUM099`` (flew on Apollo 11) has no extended missions: it rejects
  their erasable load, so scripts that need one are blocked, and the
  test that asks for one fails.
- ``LUM131`` (Apollo 13) has extended missions, with a defect invented for
  this example: it computes the propellant remaining against the standard
  mission's load.
- ``LUM210`` (Apollo 15 to 17) fixes it. It is the default.

The **mission** is not a version: it is the erasable load and the vehicle,
chosen when the LM boots, as is the **start point**. A script that needs
more than one mission, start point or abort altitude has a variation for
each; cases that can run one after another on the same flight are rows of
a table block instead.

What each script shows
----------------------

=========================  ======================================  ==========================
Script                     Shows                                   Outcome
=========================  ======================================  ==========================
DSKY/tc_dsky_001           a table block, refs as row values       pass
DSKY/tc_dsky_002           a table of bad entries                  pass
DSKY/tc_dsky_003           rules as a defn, checked per row        pass
DSKY/tc_dsky_004           an ``lms``-only script, Wait timing     pass (``lms`` only)
DSKY/tc_dsky_005           a precondition after a step             refuses to queue
GDN/tc_gdn_001             ignition on PRO, flashing V99 N62       pass
GDN/tc_gdn_002             mission variations, the whole flight    pass; extended blocked
                                                                   on LUM099
GDN/tc_gdn_003             ``:definitions:`` per variation,        pass; extended blocked
                           ``rvt-variant``, folder ``core.rst``    on LUM099
GDN/tc_gdn_004             flying P66 by hand, a table of clicks   pass
GDN/tc_gdn_005             the hands-off crew, P65 and P68         pass
GDN/tc_gdn_006             V57, N68, a bench fault                 pass
GDN/tc_gdn_007             a flow of ``(TBD)`` steps               incomplete
LND/tc_lnd_001             mission × start point variations,       pass; extended blocked
                           attachments, prose per variation        on LUM099
LND/tc_lnd_002             seed variations; filter by ``index``    pass
ABT/tc_abt_001             abort altitude variations, ``import``   pass
ABT/tc_abt_002             panel switches, the staging interlock   pass
ABT/tc_abt_003             SetFixedValue, ``try-ok?``,             pass
                           ``quietly``
ALM/tc_alm_001             Apollo 11's 1202s                       pass
ALM/tc_alm_002             caution and the master alarm            pass
ALM/tc_alm_003             the defect in LUM131                    **fails on LUM131,
                                                                   extended**; extended
                                                                   blocked on LUM099
CFG/tc_cfg_001             load × vehicle variations               pass; extended loads
                                                                   blocked on LUM099
CFG/tc_cfg_002             a handle call as a check                **fails on LUM099**
SFC/tc_sfc_001             a three-day stay, ``sim`` only          pass; extended blocked
                                                                   on LUM099
SFC/tc_sfc_002             Wait over hours                         pass
SFC/tc_sfc_003             a table with SetFixedValue              pass
ECS/tc_ecs_001..003        flows to review                         incomplete
=========================  ======================================  ==========================

Requirements without scripts
----------------------------
Verified by analysis or inspection, on purpose: ``MSN-005``,
``MSN-011``, ``MSN-012``, ``LM-GNC-003``, ``LM-ABT-003``,
``LM-PRP-002``, ``LM-PRP-004``, ``LM-EPS-001``, ``LM-EPS-003``,
``LM-ECS-001``, ``LM-ECS-003``, ``LGC-EXE-001``. ``LM-GNC-002`` (the
DSKY) and ``LM-CWS-002`` (a headset tone) are verified by
demonstration. ``LGC-DSK-005`` is removed from the specification in the
history's third run.
