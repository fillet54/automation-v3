==================
Real-Time Downlink
==================
Checks the S-band real-time telemetry rate during a simulated ground
contact.

Requirements
------------
1. :req:`VM-TM-004`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Start a simulated ground contact on the S-band RF link

   (TBD)

.. rvt:: Verify the real-time telemetry bit rate is 32 kbit/s and every housekeeping packet arrives

   (TBD)
