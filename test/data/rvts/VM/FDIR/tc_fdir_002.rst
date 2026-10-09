================
Recovery Actions
================
Declares a limit violation and checks its recovery action runs within
1 s.

Requirements
------------
1. :req:`VM-FDIR-002`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Recover

   (TBD "Drive the battery temperature to +31 degC for 3 s")
   (TBD "Verify the battery heater is off within 1 s of the violation")
