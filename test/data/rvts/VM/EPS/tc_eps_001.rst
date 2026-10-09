=============
Load Shedding
=============
Discharges the battery past each state of charge threshold and checks the
loads shed at each, then recharges it and checks nothing comes back until
commanded.

.. note::

   Fails on purpose with VM 3.1.0, which restores shed loads by itself
   once the battery recovers past 65% (a known defect, fixed in 3.2.0).

Requirements
------------
1. :req:`VM-EPS-001`
2. :req:`VM-EPS-002`
3. :req:`VM-EPS-003`

.. rvt::

   (variations "soc-percent shed"
     ["above-all"   [65.0 :none]
      "below-60"    [59.0 :payload]
      "below-50"    [49.0 :non-essential-heaters]
      "below-40"    [39.0 :all-but-essential]
      "at-40"       [40.0 :non-essential-heaters]])

   (Precondition "Platform in NOMINAL"
     (platform-in-mode? :nominal)
     :heal "Command the platform to NOMINAL"
     (command-mode :nominal))

Steps
-----

.. rvt:: The table follows the requirement

   (Verify (loads-shed soc-percent) = shed)

.. rvt:: Start from a known state

   (.set_sun vm false)
   (Verify (SendTC :restore-loads) = :executed)
   (Verify (SendTC :line-on :line :payload) = :executed)

.. rvt:: State of charge

   (.set_battery vm 70.0)
   (RunFor 1)
   (Verify (Telemetry :soc) = 70.0)
   (Verify (Telemetry :shed) = :none)

.. rvt:: Discharge

   (.discharge_to vm soc-percent 2.0)
   (RunFor (* 30 (- 70.0 soc-percent)))
   (RunFor 5)
   (Verify (Telemetry :soc) = soc-percent)
   (Verify (Telemetry :shed) = shed)
   (Verify (line-on? :payload) = (= shed :none))
   (Verify (line-on? :bus-computer))

.. rvt:: Recharge

   (.set_sun vm true)
   (RunFor 8000)
   (Verify (Telemetry :soc) >= 80.0)
   (Verify (Telemetry :shed) = shed)

.. rvt:: Restore by command

   (Verify (SendTC :restore-loads) = :executed)
   (Verify (Telemetry :shed) = :none)
