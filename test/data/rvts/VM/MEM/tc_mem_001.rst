=============
Packet Stores
=============
Checks the packet stores, their capacity for 72 hours of housekeeping,
and the X-band downlink and its retention until confirmed.

Requirements
------------
1. :req:`VM-MEM-001`
2. :req:`VM-MEM-002`
3. :req:`VM-MEM-003`

.. rvt::

   (Precondition "Platform in NOMINAL"
     (platform-in-mode? :nominal)
     :heal "Command the platform to NOMINAL"
     (command-mode :nominal))

Steps
-----

.. rvt:: The housekeeping store is big enough

   (Verify (housekeeping-hours hk-store-bytes hk-bytes-per-second) >= 72)

.. rvt:: Separate stores

   (TBD "Clear all packet stores, run 10 minutes, and dump the store directory")
   (TBD "Verify housekeeping, event and payload packets are each in their own store")

.. rvt:: 72 hours

   (TBD "Run for 73 hours of simulated time at the default housekeeping rates")
   (TBD "Verify the housekeeping store has not wrapped before 72 hours")

.. rvt:: Downlink

   (TBD "Start an X-band contact and command the housekeeping store downlink")
   (TBD "Verify packets arrive oldest first at up to 2 Mbit/s")
   (TBD "Verify the store keeps them until the ground confirmation telecommand, then frees them")
