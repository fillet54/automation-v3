==========================
Commanded Mode Transitions
==========================
Commands every mode transition, allowed or not, and checks only the
allowed ones are made: an allowed one is executed and reported as a mode
transition event; any other is rejected and leaves the mode as it was.

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

.. rvt:: Out of LAUNCH's minimum time

   (if (= from :launch)
     (RunFor (* 60 launch-mode-minimum-min)))

.. rvt:: Command the transition

   (def sent-at (now))
   (Verify (SendTC :set-mode :mode to) = (if allowed :executed :rejected-transition))

.. rvt:: The mode after

   (Verify (Telemetry :mode) = (if allowed to from))
   (Verify (.had_event vm (if allowed :mode-transition :tc-rejection) sent-at))
