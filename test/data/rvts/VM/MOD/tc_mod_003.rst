=======================
Launch Mode and Resets
=======================
Checks LAUNCH mode after separation, and the mode the VM comes back in
after each kind of processor reset.

Requirements
------------
1. :req:`VM-MOD-002`
2. :req:`VM-MOD-007`

.. rvt::

   (variations "before cause after"
     ["nominal-commanded"   [:nominal :commanded :nominal]
      "nominal-power-on"    [:nominal :power-on :nominal]
      "nominal-watchdog"    [:nominal :watchdog :safe]
      "standby-exception"   [:standby :exception :safe]
      "maneuver-commanded"  [:maneuver :commanded :maneuver]])

Steps
-----

.. rvt:: The table follows the requirement

   (Verify (mode-after-reset before cause) = after)

.. rvt:: First boot after separation

   (.separate vm)
   (Verify (Telemetry :mode) = :launch)
   (RunFor (- (* 60 launch-mode-minimum-min) 60))
   (Verify (SendTC :set-mode :mode :safe) = :rejected-launch-minimum)
   (RunFor 60)
   (Verify (SendTC :set-mode :mode :safe) = :executed)
   (Verify (Telemetry :mode) = :safe)

.. rvt:: Reset and recover

   (command-mode before)
   (.reset vm cause)
   (Verify (Telemetry :reset-cause) = cause)
   (Verify (Telemetry :mode) = after)
