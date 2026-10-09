====================
Minor Frame Overruns
====================
Checks no minor frame overruns in normal running, then forces one and
checks it is counted and reported.

Requirements
------------
1. :req:`VM-EXE-002`

.. rvt::

   (Precondition "Platform in NOMINAL"
     (platform-in-mode? :nominal)
     :heal "Command the platform to NOMINAL"
     (command-mode :nominal))

Steps
-----

.. rvt:: No overruns

   (TBD "Record 600 major frames and verify the overrun count did not change")

.. rvt:: Force an overrun

   (TBD "Enable the test task that busy-waits 150 ms in one minor frame, once")
   (TBD "Verify the overrun count increments by exactly 1")
   (TBD "Verify an overrun event packet is generated")
