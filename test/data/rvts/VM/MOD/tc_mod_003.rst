==========================
Commanded Mode Transitions
==========================
Commands every transition out of SAFE, STANDBY, NOMINAL and MANEUVER,
allowed or not, one after the other, and checks only the allowed ones
are made. The transitions out of LAUNCH are in ``tc_mod_003b``: each
needs its own separation.

Requirements
------------
1. :req:`VM-MOD-003`

Steps
-----

.. rvt:: Each transition
   :table:

   ("from to allowed"
     ["SAFE to STANDBY"      [:safe :standby true]
      "SAFE to NOMINAL"      [:safe :nominal false]
      "SAFE to MANEUVER"     [:safe :maneuver false]
      "STANDBY to NOMINAL"   [:standby :nominal true]
      "STANDBY to MANEUVER"  [:standby :maneuver true]
      "STANDBY to SAFE"      [:standby :safe true]
      "NOMINAL to STANDBY"   [:nominal :standby true]
      "NOMINAL to MANEUVER"  [:nominal :maneuver false]
      "NOMINAL to SAFE"      [:nominal :safe true]
      "MANEUVER to STANDBY"  [:maneuver :standby true]
      "MANEUVER to NOMINAL"  [:maneuver :nominal false]
      "MANEUVER to SAFE"     [:maneuver :safe true]])

   (Verify (transition-allowed? from to) = allowed)
   (BringToMode from)
   (Verify (SendTC :set-mode :mode to) = (if allowed :executed :rejected-transition))
   (Verify (Telemetry :mode) = (if allowed to from))
   (Verify (Telemetry :last-event) = (if allowed :mode-transition :tc-rejection))
