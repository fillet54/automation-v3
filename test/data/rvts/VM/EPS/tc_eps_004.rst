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

   (SetValue bench.battery.soc 50.0)
   (SetValue bench.sun true)
   (Wait eps.soc = 95.0 :within 10h :every 1min)
   (RunFor 60)

.. rvt:: Limits

   (Verify eps.max-charge-current <= (/ battery-ah 5))
   (Verify eps.soc = 95.0)
   (Verify eps.charge-current = 0.0)
