===========================
Propulsion Only in MANEUVER
===========================
Tries to open the propulsion valve, armed, in each mode, and checks it
opens only in MANEUVER.

Requirements
------------
1. :req:`VM-AOCS-004`

Steps
-----

.. rvt:: Each mode
   :table:

   ("mode expected-result"
     ["STANDBY"  [:standby :rejected-mode]
      "NOMINAL"  [:nominal :rejected-mode]
      "MANEUVER" [:maneuver :executed]])

   (BringToMode mode)
   (Verify (SendTC :arm :command :propulsion-valve-open) = :executed)
   (Verify (SendTC :propulsion-valve-open) = expected-result)
