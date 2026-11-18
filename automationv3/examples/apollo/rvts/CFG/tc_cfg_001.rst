======================================
The Erasable Load Against The Vehicle
======================================
Boots each erasable load on each vehicle. Where they match, the computer
asks for ignition; where they don't, the propellant it expects isn't
what the gauges read, so it raises alarm 01520 and won't light the
engine.

.. note::

   With LUM099, the variations with an extended load are blocked: the
   precondition's heal can't boot a load that rope doesn't accept.

Requirements
------------
1. :req:`LGC-CFG-001`

.. rvt::

   (variations "load vehicle mismatch"
     ["standard load on a standard LM"   [:standard :standard false]
      "extended load on an extended LM"  [:extended :extended false]
      "standard load on an extended LM"  [:standard :extended true]
      "extended load on a standard LM"   [:extended :standard true]])

   (Precondition "LM at PDI with the variation's load and vehicle"
     (and (.at_start lm :pdi)
          (= (Read lgc.config.mission) load)
          (= (Read lgc.config.vehicle) vehicle))
     :heal "Boot the variation's load on its vehicle, with a manual crew"
     (StartLM {:mission load :vehicle vehicle :crew :manual}))

Steps
-----

.. rvt:: The check at P63

   (Verify (Read lgc.alarms) = (if mismatch [1520] []))
   (Verify dsky.flashing = (not mismatch))

.. rvt:: PRO lights the engine only on a match

   (Proceed)
   (RunFor 2)
   (Verify engine.descent.on = (not mismatch))
