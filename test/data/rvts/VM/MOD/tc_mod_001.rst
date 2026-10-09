==================
One Mode at a Time
==================
Brings the platform to each mode in turn and checks the VM reports
exactly that mode, and only ever one of the five. LAUNCH, which only
follows separation, is checked in ``tc_mod_002``.

Requirements
------------
1. :req:`VM-MOD-001`

Steps
-----

.. rvt:: Each mode
   :table:

   ("target"
     ["SAFE"     [:safe]
      "STANDBY"  [:standby]
      "NOMINAL"  [:nominal]
      "MANEUVER" [:maneuver]])

   (BringToMode target)
   (Verify (Telemetry :mode) = target)
   (Verify (known-mode? (Telemetry :mode)))
