===================================
Battery and Propulsion Temperatures
===================================
Runs the cold case in each mode and checks the battery and propulsion
temperatures stay within limits.

Requirements
------------
1. :req:`VM-TCS-004`

Steps
-----

.. rvt:: Each mode
   :table:

   ("mode"
     ["SAFE"     [:safe]
      "STANDBY"  [:standby]
      "NOMINAL"  [:nominal]
      "MANEUVER" [:maneuver]])

   (BringToMode mode)
   (TBD "Run the thermal simulator's cold case for 10 orbits")
   (TBD "Verify the battery stays between 0 and +30 degC, and the propulsion tank and lines above +10 degC")
