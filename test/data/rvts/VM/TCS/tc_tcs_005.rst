===================
Six Heaters at Most
===================
Drives every heater circuit below its lower set point and checks no
more than six are on at once.

Requirements
------------
1. :req:`VM-TCS-005`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: All cold

   (TBD "Drive the control sensors of all ten heater circuits below their lower set points")
   (TBD "Verify no more than heater-limit (6) heaters are on at any time")
