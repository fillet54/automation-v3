===================
Repeated Recoveries
===================
Triggers the same recovery four times in an hour and checks the fourth
waits for a telecommand.

Requirements
------------
1. :req:`VM-FDIR-006`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Four times

   (TBD "Trigger the battery temperature violation four times within one hour")
   (TBD "Verify the recovery action ran three times and the fourth is held")
   (TBD "Acknowledge by telecommand and verify the fourth runs")
