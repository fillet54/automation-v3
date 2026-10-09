========================
Load Shedding Thresholds
========================
Discharges the battery past each state of charge threshold, one after
the other, and checks the loads shed at each.

Requirements
------------
1. :req:`VM-EPS-002`

.. rvt::

   (Precondition "Platform in NOMINAL"
     (platform-in-mode? :nominal)
     :heal "Command the platform to NOMINAL"
     (command-mode :nominal))

Steps
-----

.. rvt:: Each threshold
   :table:

   ("soc-percent shed"
     ["above-all" [65.0 :none]
      "below-60"  [59.0 :payload]
      "below-50"  [49.0 :non-essential-heaters]
      "at-40"     [40.0 :non-essential-heaters]
      "below-40"  [39.0 :all-but-essential]])

   (Verify (loads-shed soc-percent) = shed)
   (.set_sun vm false)
   (SendTC :restore-loads)
   (.set_battery vm 70.0)
   (.discharge_to vm soc-percent 2.0)
   (RunFor (+ 5 (* 30 (- 70.0 soc-percent))))
   (Verify (Telemetry :soc) = soc-percent)
   (Verify (Telemetry :shed) = shed)
   (Verify (line-on? :bus-computer))
