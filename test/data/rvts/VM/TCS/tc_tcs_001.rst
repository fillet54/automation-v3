==================
Heater Thermostats
==================
Drives a heater circuit's control temperature through its set points and
checks the thermostat, sensor redundancy, and the six heater limit.

Requirements
------------
1. :req:`VM-TCS-001`
2. :req:`VM-TCS-002`
3. :req:`VM-TCS-003`
4. :req:`VM-TCS-005`

.. rvt::

   (variations "temperature was-on heater-on"
     ["below-lower"  [4.0 false true]
      "in-band-on"   [6.0 true true]
      "in-band-off"  [6.0 false false]
      "above-upper"  [9.0 true false]])

   (def lower-set-point 5.0)
   (def upper-set-point 8.0)

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: The table follows the requirement

   (Verify (heater-on? temperature lower-set-point upper-set-point was-on) = heater-on)

.. rvt:: Thermostat

   (TBD "Load set points 5 degC and 8 degC for the battery heater in STANDBY")
   (TBD "Put the heater in the was-on state, then drive its control sensor to the variation's temperature")
   (TBD "Verify the heater is on exactly when heater-on")

.. rvt:: A failed sensor

   (TBD "Drive the control sensor to -70 degC (out of range) and the redundant sensor to +6 degC")
   (TBD "Verify the thermostat now follows the redundant sensor")

.. rvt:: Six heaters at most

   (TBD "Drive the control sensors of all ten heater circuits below their lower set points")
   (TBD "Verify no more than heater-limit (6) heaters are on at any time")
