===================================
Commanded Transitions Out of LAUNCH
===================================
Commands each transition out of LAUNCH, after LAUNCH's minimum time.
Each case is a variation, not a table row: LAUNCH is entered only on the
first boot after separation, so every case needs its own.

Requirements
------------
1. :req:`VM-MOD-003`

.. rvt::

   (variations "to allowed"
     ["LAUNCH to SAFE"     [:safe true]
      "LAUNCH to STANDBY"  [:standby false]
      "LAUNCH to NOMINAL"  [:nominal false]])

Steps
-----

.. rvt:: Separation

   (.separate vm)
   (RunFor (* 60 launch-mode-minimum-min))

.. rvt:: The transition

   (Verify (transition-allowed? :launch to) = allowed)
   (Verify (SendTC :set-mode :mode to) = (if allowed :executed :rejected-transition))
   (Verify (Telemetry :mode) = (if allowed to :launch))
