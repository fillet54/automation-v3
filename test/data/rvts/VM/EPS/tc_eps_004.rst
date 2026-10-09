================
Battery Charging
================
Charges the battery from 50% in full sunlight and checks the charge
current never exceeds C/5 and charging stops at 95%.

Requirements
------------
1. :req:`VM-EPS-004`

.. rvt::

   (def battery-ah 40.0)

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Charge

   (.set_battery vm 50.0)
   (.set_sun vm true)
   (RunFor 36000)

.. rvt:: Limits

   (Verify (Telemetry :max-charge-current) <= (/ battery-ah 5))
   (Verify (Telemetry :soc) = 95.0)
   (Verify (Telemetry :charge-current) = 0.0)
