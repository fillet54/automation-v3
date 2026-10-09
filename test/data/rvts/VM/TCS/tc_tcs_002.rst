======================
Thermal Limits by Mode
======================
Runs a cold case in each mode and checks the battery and propulsion
temperatures stay within their limits.

Requirements
------------
1. :req:`VM-TCS-004`

.. rvt::

   (variations "mode"
     ["safe"     [:safe]
      "standby"  [:standby]
      "nominal"  [:nominal]
      "maneuver" [:maneuver]])

   (Precondition "Platform in the variation's mode"
     (platform-in-mode? mode)
     :heal "Command the platform to the mode"
     (command-mode mode))

Steps
-----

.. rvt:: Cold case

   (TBD "Run the thermal simulator's cold case (eclipse season, minimum power) for 10 orbits")
   (TBD "Verify the battery stays between 0 degC and +30 degC")
   (TBD "Verify the propulsion tank and lines stay above +10 degC")
