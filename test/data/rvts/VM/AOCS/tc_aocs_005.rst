=============
Ending a Burn
=============
Commands burns at nominal and half thrust and checks each ends at its
delta-v, or at 110% of its commanded time.

Requirements
------------
1. :req:`VM-AOCS-005`

.. rvt::

   (Precondition "Platform in MANEUVER"
     (platform-in-mode? :maneuver)
     :heal "Command the platform to MANEUVER"
     (command-mode :maneuver))

Steps
-----

.. rvt:: Each burn
   :table:

   ("commanded-s thrust ends-at-s"
     ["nominal thrust" [100.0 :nominal 100.0]
      "half thrust"    [100.0 :half 110.0]])

   (Verify (if (= thrust :half) (burn-time-limit-s commanded-s) commanded-s) = ends-at-s)
   (TBD "Set the simulated thruster to the row's thrust level")
   (TBD "Command a burn sized for commanded-s seconds at nominal thrust")
   (TBD "Verify the burn ends at ends-at-s seconds, within 0.1 s")
