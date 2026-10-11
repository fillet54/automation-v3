=============================
Rate Damping After Separation
=============================
Replays separation with the platform tumbling and checks rate damping,
then Sun acquisition once the rates are low for 60 s.

Requirements
------------
1. :req:`VM-AOCS-003`

Steps
-----

.. rvt:: Tumbling

   (.separate vm)

.. rvt:: Start the dynamics simulator tumbling at 3 deg/s per axis

   (TBD)

.. rvt:: Verify the VM commands rate damping

   (TBD)

.. rvt:: Verify Sun acquisition is commanded only after all body rates stay below body-rate-limit-dps (0.5 deg/s) for 60 s

   (TBD)
