======================
Packet Sequence Counts
======================
Checks sequence counts increase by one per packet and wrap after
16383.

Requirements
------------
1. :req:`VM-TM-007`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Sequence counts wrap as specified

   (Verify (next-sequence-count 0) = 1)
   (Verify (next-sequence-count max-sequence-count) = 0)

.. rvt:: Set the power housekeeping packet to 10 Hz

   (TBD)

.. rvt:: Record until its count reaches max-sequence-count, verifying no gaps

   (TBD)

.. rvt:: Verify the next packet's count is 0

   (TBD)
