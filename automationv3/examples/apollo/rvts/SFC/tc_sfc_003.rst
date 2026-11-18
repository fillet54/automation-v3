====================
Bus Voltage Cautions
====================
Loads the bus from the bench, more each time, and checks the BATTERY
caution comes on below 26.5 V and the WARNING below 24 V.

Requirements
------------
1. :req:`LM-EPS-002`

.. rvt::

   (Precondition "LM on the surface, the crew's part left to the script"
     (lm-ready-for? :standard :surface :manual)
     :heal "Boot a standard mission on the surface with a manual crew"
     (boot-for :standard :surface :manual))

Steps
-----

.. rvt:: Each load
   :table:

   ("extra-amps caution warning"
     ["normal"   [0   false false]
      "heavy"    [200 true  false]
      "overload" [300 true  true]])

   (SetFixedValue bench.bus-load-amps extra-amps)
   (RunFor 60)
   (Verify cwea.light.battery = caution)
   (Verify cwea.warning = warning)
   (if caution
     (Verify eps.bus-volts < 26.5)
     (Verify eps.bus-volts >= 26.5))
   (ClearFixedValue bench.bus-load-amps)
   (RunFor 60)
