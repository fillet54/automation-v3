==============
Processor Load
==============
Measures the processor load in each mode and checks it stays under
70% averaged over every major frame.

Requirements
------------
1. :req:`VM-EXE-007`

Steps
-----

.. rvt:: Each mode
   :table:

   ("mode"
     ["SAFE"     [:safe]
      "STANDBY"  [:standby]
      "NOMINAL"  [:nominal]
      "MANEUVER" [:maneuver]])

   (BringToMode mode)
   (TBD "Record the processor load telemetry for 600 major frames")
   (TBD "Verify the load averaged over each major frame never exceeded max-cpu-load (70%)")
