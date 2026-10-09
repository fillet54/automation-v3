==============================
Attitude Mode by Platform Mode
==============================
Brings the platform to each mode and checks the attitude mode the VM
commands.

Requirements
------------
1. :req:`VM-AOCS-002`

Steps
-----

.. rvt:: Each mode
   :table:

   ("mode attitude"
     ["SAFE"     [:safe :sun-pointing]
      "STANDBY"  [:standby :nadir-pointing]
      "NOMINAL"  [:nominal :nadir-pointing]
      "MANEUVER" [:maneuver :inertial]])

   (BringToMode mode)
   (Verify (Telemetry :attitude-mode) = attitude)
   (TBD "Verify the attitude error settles below 1 deg within 10 minutes on the dynamics simulator")
