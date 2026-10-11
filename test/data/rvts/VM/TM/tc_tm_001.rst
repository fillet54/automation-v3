====================
Housekeeping Packets
====================
Decodes a minute of housekeeping telemetry and checks every packet is a
valid CCSDS space packet.

Requirements
------------
1. :req:`VM-TM-001`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Record 60 s of housekeeping telemetry

   (TBD)

.. rvt:: Verify every packet decodes as a CCSDS space packet: version, APID, sequence flags and length

   (TBD)
