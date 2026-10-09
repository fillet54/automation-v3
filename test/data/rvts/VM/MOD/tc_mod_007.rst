==================
Mode After a Reset
==================
Resets the bus computer in each way, from a mode, and checks the mode
it comes back in: the same, except SAFE after a watchdog or exception
reset.

Requirements
------------
1. :req:`VM-MOD-007`

Steps
-----

.. rvt:: Each reset
   :table:

   ("before cause after"
     ["NOMINAL, commanded"  [:nominal :commanded :nominal]
      "NOMINAL, power-on"   [:nominal :power-on :nominal]
      "NOMINAL, watchdog"   [:nominal :watchdog :safe]
      "STANDBY, exception"  [:standby :exception :safe]
      "MANEUVER, commanded" [:maneuver :commanded :maneuver]])

   (Verify (mode-after-reset before cause) = after)
   (BringToMode before)
   (.reset vm cause)
   (Verify (Telemetry :reset-cause) = cause)
   (Verify (Telemetry :mode) = after)
