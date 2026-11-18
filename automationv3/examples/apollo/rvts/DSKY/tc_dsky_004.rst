==========================
Monitor And Display Timing
==========================
Checks that V16 updates its noun every guidance cycle, and that V06
holds the values of the moment it was keyed.

Runs only on the mission simulator, where time runs on its own and the
crew sees the display change as it would in flight.

Requirements
------------
1. :req:`LGC-DSK-003`

.. rvt::

   (environments :lms)

   (Precondition "LM at PDI, the DSKY left to the script"
     (lm-ready-for? :standard :pdi :manual)
     :heal "Boot a standard mission at PDI with a manual crew"
     (boot-for :standard :pdi :manual))

Steps
-----

.. rvt:: V16 updates

   (Proceed)
   (Keys "V16N68E")
   (let [range (Read dsky.r1)]
     (Wait dsky.r1 not= range :within 3s :every 100ms))

.. rvt:: V06 holds

   (Keys "V06N68E")
   (let [range (Read dsky.r1)]
     (Wait 5s)
     (Verify dsky.r1 = range))
