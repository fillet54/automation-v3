=================
Heater Thermostat
=================
Drives a heater's control temperature through its set points and checks
the heater switches on below the lower and off above the upper.

Requirements
------------
1. :req:`VM-TCS-002`

.. rvt::

   (def lower-set-point 5.0)
   (def upper-set-point 8.0)

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Each temperature
   :table:

   ("temperature was-on heater-on"
     ["below lower"   [4.0 false true]
      "in band, on"   [6.0 true true]
      "in band, off"  [6.0 false false]
      "above upper"   [9.0 true false]])

   (Verify (heater-on? temperature lower-set-point upper-set-point was-on) = heater-on)
   (TBD "Put the battery heater in the was-on state, then drive its control sensor to temperature")
   (TBD "Verify the heater is on exactly when heater-on")
