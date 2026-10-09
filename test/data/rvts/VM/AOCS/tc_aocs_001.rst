==============
AOCS Task Rate
==============
Checks the AOCS control task runs at 10 Hz in every mode.

Requirements
------------
1. :req:`VM-AOCS-001`

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
   (TBD "Record the AOCS task execution times for 60 s and verify a 10 Hz rate")
