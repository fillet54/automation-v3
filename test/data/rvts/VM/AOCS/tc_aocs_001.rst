==============================
Attitude Mode by Platform Mode
==============================
Checks the AOCS control task rate in every mode, the attitude mode the VM
commands for each platform mode, and rate damping out of LAUNCH.

Requirements
------------
1. :req:`VM-AOCS-001`
2. :req:`VM-AOCS-002`
3. :req:`VM-AOCS-003`

.. rvt::

   (variations "mode attitude"
     ["safe"     [:safe :sun-pointing]
      "standby"  [:standby :nadir-pointing]
      "nominal"  [:nominal :nadir-pointing]
      "maneuver" [:maneuver :inertial]])

   (Precondition "Platform in the variation's mode"
     (platform-in-mode? mode)
     :heal "Command the platform to the mode"
     (command-mode mode))

Steps
-----

.. rvt:: Control rate and attitude

   (TBD "Record the AOCS task execution times for 60 s and verify a 10 Hz rate")
   (TBD "Verify the commanded AOCS mode is the variation's attitude")
   (TBD "Verify the attitude error settles below 1 deg within 10 minutes on the dynamics simulator")

.. rvt-variant::
   :variations: safe

   From SAFE, the test also replays LAUNCH.

   .. rvt:: Rate damping after separation

      (TBD "Start the dynamics simulator tumbling at 3 deg/s per axis, in LAUNCH mode")
      (TBD "Verify the VM commands rate damping")
      (TBD "Verify Sun acquisition is commanded only after all body rates stay below body-rate-limit-dps (0.5 deg/s) for 60 s")
