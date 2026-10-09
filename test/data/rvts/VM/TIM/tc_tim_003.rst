=================
Free-Running Time
=================
Removes the GNSS fix and checks time keeps running from the
oscillator, with the time since synchronisation reported.

Requirements
------------
1. :req:`VM-TIM-003`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: No fix

   (TBD "Remove the GNSS fix for 6 hours")
   (TBD "Verify the time since last synchronisation in telemetry grows from 0 to 6 hours")
