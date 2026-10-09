============================
Redundant Temperature Sensor
============================
Drives a heater's control sensor out of range and checks the
thermostat follows the redundant sensor.

Requirements
------------
1. :req:`VM-TCS-003`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Each reading
   :table:

   ("reading"
     ["too cold" [-70.0]
      "too hot"  [110.0]])

   (TBD "Drive the control sensor to reading and the redundant sensor to +6 degC")
   (TBD "Verify the thermostat follows the redundant sensor")
