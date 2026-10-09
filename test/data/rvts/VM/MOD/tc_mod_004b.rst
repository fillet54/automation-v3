============================
No Autonomous SAFE in LAUNCH
============================
Holds an attitude error in LAUNCH and checks the VM does not leave it:
LAUNCH is the one mode FDIR can't take the platform out of.

Requirements
------------
1. :req:`VM-MOD-004`

Steps
-----

.. rvt:: In LAUNCH

   (.separate vm)
   (.inject vm :attitude-error 15.0)
   (RunFor 120)
   (Verify (Telemetry :mode) = :launch)
   (.inject vm :attitude-error 0.0)
