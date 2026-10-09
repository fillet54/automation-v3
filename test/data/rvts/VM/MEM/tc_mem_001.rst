=============
Packet Stores
=============
Checks housekeeping, events and payload data go to separate packet
stores.

Requirements
------------
1. :req:`VM-MEM-001`

.. rvt::

   (Precondition "Platform in NOMINAL"
     (platform-in-mode? :nominal)
     :heal "Command the platform to NOMINAL"
     (command-mode :nominal))

Steps
-----

.. rvt:: Separate stores

   (TBD "Clear all packet stores, run 10 minutes, and dump the store directory")
   (TBD "Verify housekeeping, event and payload packets are each in their own store")
