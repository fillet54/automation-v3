========================
Cyclic Schedule and Load
========================
Runs the VM in each mode and checks its cyclic schedule: ten 100 ms minor
frames per 1 s major frame, no overruns, and processor load under 70%.
Then forces an overrun and checks it is counted and reported.

Requirements
------------
1. :req:`VM-EXE-001`
2. :req:`VM-EXE-002`
3. :req:`VM-EXE-007`

.. rvt::

   (variations "mode"
     ["safe"     [:safe]
      "standby"  [:standby]
      "nominal"  [:nominal]
      "maneuver" [:maneuver]])

   (Precondition "Platform in the variation's mode"
     (platform-in-mode? mode)
     :heal "Command the platform to the mode"
     (command-mode mode))

Steps
-----

.. rvt:: The frame timing adds up

   (Verify (* minor-frame-ms minor-frames-per-major) = 1000)

.. rvt:: Measure the schedule

   (TBD "Enable the schedule trace telemetry at 10 Hz")
   (TBD "Record 600 major frames (10 minutes)")
   (TBD "Verify every major frame holds 10 minor frames, each starting 100 ms +/- 1 ms after the last")
   (TBD "Verify the minor frame overrun count did not change")
   (TBD "Verify the processor load averaged over each major frame never exceeded max-cpu-load (70%)")

.. rvt:: Force an overrun

   (TBD "Enable the test task that busy-waits 150 ms in one minor frame, once")
   (TBD "Verify the overrun count increments by exactly 1")
   (TBD "Verify an overrun event packet is generated")
