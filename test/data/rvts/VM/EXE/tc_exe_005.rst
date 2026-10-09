===========
Reset Cause
===========
Resets the bus computer in each way and checks the cause is recorded
and reported after the next boot.

Requirements
------------
1. :req:`VM-EXE-005`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Each kind of reset
   :table:

   ("cause"
     ["power-on"  [:power-on]
      "watchdog"  [:watchdog]
      "commanded" [:commanded]
      "exception" [:exception]])

   (TBD "Cause the row's reset")
   (TBD "Verify the reset cause in telemetry after boot is the row's cause")
