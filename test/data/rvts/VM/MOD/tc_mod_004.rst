=============================
Autonomous SAFE From Any Mode
=============================
From each mode other than LAUNCH, holds an attitude error until FDIR
requests SAFE, and checks the VM goes to SAFE. LAUNCH is in
``tc_mod_004b``.

Requirements
------------
1. :req:`VM-MOD-004`

Steps
-----

.. rvt:: Each mode
   :table:

   ("from"
     ["STANDBY"  [:standby]
      "NOMINAL"  [:nominal]
      "MANEUVER" [:maneuver]])

   (BringToMode from)
   (.inject vm :attitude-error 15.0)
   (RunFor 61)
   (Verify (Telemetry :mode) = :safe)
   (.inject vm :attitude-error 0.0)
