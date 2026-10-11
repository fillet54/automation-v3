=====================
Packet Store Downlink
=====================
Downlinks the housekeeping store and checks the order, the rate, and
that packets are kept until the ground confirms them.

Requirements
------------
1. :req:`VM-MEM-003`

.. rvt::

   (Precondition "Platform in NOMINAL"
     (platform-in-mode? :nominal)
     :heal "Command the platform to NOMINAL"
     (command-mode :nominal))

Steps
-----

.. rvt:: Start an X-band contact and command the housekeeping store downlink

   (TBD)

.. rvt:: Verify packets arrive oldest first at up to 2 Mbit/s

   (TBD)

.. rvt:: Verify the store keeps them until the ground confirmation telecommand, then frees them

   (TBD)
