======================
Launch Mode and Resets
======================
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

   (TBD "Set the separation switches to separated and clear the first-boot flag")
   (power-cycle-bus-computer)
   (TBD "Verify the mode is LAUNCH")
   (TBD "Command SAFE before launch-mode-minimum-min (30 min) and verify it is rejected")
   (TBD "Wait 30 minutes, command SAFE and verify the mode becomes SAFE")

.. rvt:: Reset and recover

   (command-mode before)
   (TBD "Cause the variation's reset")
   (TBD "Verify the mode after boot is the variation's after mode")
