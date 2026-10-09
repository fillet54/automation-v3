===============
State of Charge
===============
Sets the battery simulator to several states of charge and checks the
VM's state of charge follows within one major frame.

Requirements
------------
1. :req:`VM-EPS-001`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Start from a known state

   (SetValue bench.sun false)
   (Verify (SendTC :restore-loads) = :executed)
   (Verify (SendTC :line-on :line :payload) = :executed)

.. rvt:: Each state of charge
   :table:

   ("soc-percent"
     ["full"  [95.0]
      "mid"   [70.0]
      "low"   [45.0]])

   (SetValue bench.battery.soc soc-percent)
   (RunFor 1)
   (Verify eps.soc = soc-percent)
