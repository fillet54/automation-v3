==============================
Real-Time, Recorded and Events
==============================
Checks the S-band real-time downlink during a contact, that housekeeping
is recorded whether or not there is a contact, and that each kind of
event produces an event packet within 1 s.

Requirements
------------
1. :req:`VM-TM-004`
2. :req:`VM-TM-005`
3. :req:`VM-TM-006`

.. rvt::

   (variations "event-trigger"
     ["mode-transition"   [:command-standby-to-safe]
      "tc-rejection"      [:send-bad-crc]
      "fault-recovery"    [:inject-transponder-a-failure]
      "limit-violation"   [:raise-battery-temperature]])

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Contact and no contact

   (TBD "Start a simulated ground contact on the S-band RF link")
   (TBD "Verify the real-time telemetry bit rate is 32 kbit/s and every housekeeping packet arrives")
   (TBD "End the contact for 10 minutes, then dump the housekeeping packet store")
   (TBD "Verify the store holds every housekeeping packet from during and after the contact")

.. rvt:: Event packet

   (TBD "Trigger the variation's event")
   (TBD "Verify the matching event packet arrives within 1 s of the trigger")
