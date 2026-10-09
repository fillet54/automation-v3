=============
Event Packets
=============
Causes each kind of event and checks its event packet arrives within
1 s.

Requirements
------------
1. :req:`VM-TM-006`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Each event
   :table:

   ("trigger"
     ["mode transition"  [:command-standby-to-safe]
      "TC rejection"     [:send-bad-crc]
      "fault recovery"   [:inject-transponder-a-failure]
      "limit violation"  [:raise-battery-temperature]])

   (TBD "Cause the row's event")
   (TBD "Verify the matching event packet arrives within 1 s")
