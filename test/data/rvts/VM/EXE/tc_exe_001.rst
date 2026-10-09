===============
Cyclic Schedule
===============
Records the schedule trace for ten minutes and checks every major
frame holds ten 100 ms minor frames.

Requirements
------------
1. :req:`VM-EXE-001`

.. rvt::

   (Precondition "Platform in NOMINAL"
     (platform-in-mode? :nominal)
     :heal "Command the platform to NOMINAL"
     (command-mode :nominal))

Steps
-----

.. rvt:: The frame timing adds up

   (Verify (* minor-frame-ms minor-frames-per-major) = 1000)

.. rvt:: Measure the schedule

   (TBD "Enable the schedule trace telemetry at 10 Hz")
   (TBD "Record 600 major frames (10 minutes)")
   (TBD "Verify every major frame holds 10 minor frames, each starting 100 ms +/- 1 ms after the last")
