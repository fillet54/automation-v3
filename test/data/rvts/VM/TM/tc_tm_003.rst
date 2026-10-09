=====================
Telemetry Time Stamps
=====================
Checks each housekeeping packet's time stamp against the bench's record
of when its data was sampled.

Requirements
------------
1. :req:`VM-TM-003`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Time stamps

   (TBD "Record 60 s of housekeeping with the bench's sampling time record")
   (TBD "Verify each packet's time stamp is within 1 ms of its sampling time")
