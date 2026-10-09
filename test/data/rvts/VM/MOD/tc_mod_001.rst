==========================
Commanded Mode Transitions
==========================
Commands every mode transition, allowed or not, and checks only the
allowed ones are made.

Requirements
------------
1. :req:`VM-MOD-001`
2. :req:`VM-MOD-003`

.. rvt::

   (variations "from to allowed"
     ["LAUNCH to SAFE"       [:launch :safe true]
      "LAUNCH to STANDBY"    [:launch :standby false]
      "SAFE to STANDBY"      [:safe :standby true]
      "SAFE to NOMINAL"      [:safe :nominal false]
      "STANDBY to NOMINAL"   [:standby :nominal true]
      "STANDBY to MANEUVER"  [:standby :maneuver true]
      "STANDBY to SAFE"      [:standby :safe true]
      "NOMINAL to STANDBY"   [:nominal :standby true]
      "NOMINAL to MANEUVER"  [:nominal :maneuver false]
      "NOMINAL to SAFE"      [:nominal :safe true]
      "MANEUVER to STANDBY"  [:maneuver :standby true]
      "MANEUVER to NOMINAL"  [:maneuver :nominal false]
      "MANEUVER to SAFE"     [:maneuver :safe true]])

   (Precondition "Platform in the variation's starting mode"
     (platform-in-mode? from)
     :heal "Bring the platform to the starting mode through allowed transitions"
     (command-mode from))

Steps
-----

.. rvt:: The table follows the requirement

   (Verify (transition-allowed? from to) = allowed)

.. rvt:: Command the transition

   (TBD "Send the mode transition telecommand for the variation's to mode")
   (TBD "If allowed, verify the mode becomes to within 1 s and a mode transition event is generated")
   (TBD "If not allowed, verify the telecommand is rejected and the mode is still from")
   (TBD "Verify exactly one mode is reported active throughout")
