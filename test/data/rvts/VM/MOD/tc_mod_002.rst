============================
Launch Mode After Separation
============================
Replays separation and checks the VM boots into LAUNCH and stays there
for at least 30 minutes, refusing to leave before.

Requirements
------------
1. :req:`VM-MOD-002`

Steps
-----

.. rvt:: First boot after separation

   (.separate vm)
   (Verify (Telemetry :mode) = :launch)

.. rvt:: Not before 30 minutes

   (RunFor (- (* 60 launch-mode-minimum-min) 60))
   (Verify (SendTC :set-mode :mode :safe) = :rejected-launch-minimum)
   (Verify (Telemetry :mode) = :launch)

.. rvt:: After 30 minutes

   (RunFor 60)
   (Verify (SendTC :set-mode :mode :safe) = :executed)
   (Verify (Telemetry :mode) = :safe)
