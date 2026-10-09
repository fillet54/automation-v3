=============
Load Shedding
=============
Discharges the battery past each state of charge threshold and checks the
loads shed at each, and that nothing comes back until commanded.

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

.. rvt:: State of charge

   (TBD "Set the battery simulator to a known 70% state of charge")
   (TBD "Verify the reported state of charge is 70% +/- 2% and updates every major frame")

.. rvt:: Discharge

   (TBD "Discharge the battery simulator to soc-percent at 2% per minute")
   (TBD "Verify exactly the loads for shed are off, and each was shed in the load shedding table's order")

.. rvt:: Recharge

   (TBD "Charge back to 80%")
   (TBD "Verify the shed loads are still off")
   (TBD "Command each shed load on and verify it powers on")
