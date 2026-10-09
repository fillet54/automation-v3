====================
Propulsion and Burns
====================
Checks propulsion is enabled only in MANEUVER, and that a burn ends at
its delta-v, or at 110% of its commanded duration if the delta-v isn't
reached.

Requirements
------------
1. :req:`VM-AOCS-004`
2. :req:`VM-AOCS-005`

.. rvt::

   (variations "commanded-s thrust ends-at-s"
     ["nominal-thrust" [100.0 :nominal 100.0]
      "weak-thrust"    [100.0 :half 110.0]])

Steps
-----

.. rvt:: The burn time limit follows the requirement

   (Verify (if (= thrust :half) (burn-time-limit-s commanded-s) commanded-s) = ends-at-s)

.. rvt:: Propulsion outside MANEUVER

   (command-mode :standby)
   (TBD "Send the arm and the propulsion valve open telecommands")
   (TBD "Verify the valve drive stays inactive and the command is rejected")

.. rvt:: A burn

   (command-mode :maneuver)
   (TBD "Set the simulated thruster to the variation's thrust level")
   (TBD "Command a burn sized for commanded-s seconds at nominal thrust")
   (TBD "Verify the burn ends at ends-at-s seconds, within 0.1 s")
