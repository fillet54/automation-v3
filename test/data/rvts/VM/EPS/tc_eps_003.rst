===================
Shed Loads Stay Off
===================
Sheds loads for a low state of charge, recharges the battery, and
checks the loads come back only when commanded.

.. note::

   Fails on purpose with VM 3.1.0, which restores shed loads by itself
   once the battery recovers past 65% (a known defect, fixed in 3.2.0).

Requirements
------------
1. :req:`VM-EPS-003`

.. rvt::

   (Precondition "Platform in NOMINAL"
     (platform-in-mode? :nominal)
     :heal "Command the platform to NOMINAL"
     (command-mode :nominal))

Steps
-----

.. rvt:: Start from a known state

   (.set_sun vm false)
   (Verify (SendTC :restore-loads) = :executed)
   (Verify (SendTC :line-on :line :payload) = :executed)

.. rvt:: Shed

   (.set_battery vm 62.0)
   (.discharge_to vm 49.0 2.0)
   (RunFor 400)
   (Verify (Telemetry :shed) = :non-essential-heaters)

.. rvt:: Recharge

   (.set_sun vm true)
   (RunFor 8000)
   (Verify (Telemetry :soc) >= 80.0)
   (Verify (Telemetry :shed) = :non-essential-heaters)

.. rvt:: Restore by command

   (Verify (SendTC :restore-loads) = :executed)
   (Verify (Telemetry :shed) = :none)
   (Verify (line-on? :payload))
