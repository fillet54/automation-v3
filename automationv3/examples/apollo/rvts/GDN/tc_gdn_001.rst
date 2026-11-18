===========================
Ignition Waits For The Crew
===========================
At powered descent initiation the computer asks for the crew's consent
with V99 N62 flashing. Waits, checks the engine stays off, then
proceeds and checks it lights at full throttle.

Requirements
------------
1. :req:`LGC-GDN-001`

.. rvt::

   (Precondition "LM at PDI, the crew's part left to the script"
     (lm-ready-for? :standard :pdi :manual)
     :heal "Boot a standard mission at PDI with a manual crew"
     (boot-for :standard :pdi :manual))

Steps
-----

.. rvt:: The computer asks

   (Verify dsky.flashing = true)
   (Verify dsky.verb = 99)
   (Verify dsky.noun = 62)

.. rvt:: Nothing happens without PRO

   (RunFor 30)
   (Verify engine.descent.on = false)
   (Verify deca.throttle = 0)

.. rvt:: PRO lights the engine

   (Proceed)
   (RunFor 1)
   (Verify engine.descent.on = true)
   (Verify deca.throttle = full-throttle)
   (Verify dsky.flashing = false)
