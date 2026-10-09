========================
72 Hours of Housekeeping
========================
Checks the housekeeping store holds 72 hours before wrapping.

Requirements
------------
1. :req:`VM-MEM-002`

.. rvt::

   (Precondition "Platform in NOMINAL"
     (platform-in-mode? :nominal)
     :heal "Command the platform to NOMINAL"
     (command-mode :nominal))

Steps
-----

.. rvt:: The store is big enough

   (Verify (housekeeping-hours hk-store-bytes hk-bytes-per-second) >= 72)

.. rvt:: 72 hours

   (TBD "Run for 73 hours of simulated time at the default housekeeping rates")
   (TBD "Verify the housekeeping store has not wrapped before 72 hours")
