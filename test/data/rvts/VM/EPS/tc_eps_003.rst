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

   (SetValue bench.sun false)
   (Verify (SendTC :restore-loads) = :executed)
   (Verify (SendTC :line-on :line :payload) = :executed)

.. rvt:: Shed

   (SetValue bench.battery.soc 62.0)
   (.discharge_to vm 49.0 2.0)
   (Wait eps.shed = :non-essential-heaters :within 10min)

.. rvt:: Recharge

   (SetValue bench.sun true)
   (Wait eps.soc >= 80.0 :within 3h :every 1min)
   (Verify eps.shed = :non-essential-heaters)

.. rvt:: Restore by command

   (Verify (SendTC :restore-loads) = :executed)
   (Verify eps.shed = :none)
   (Verify lines.payload.on)
