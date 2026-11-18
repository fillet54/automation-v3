================================
Automatic Vertical Descent (P65)
================================
With the crew's hands off, the computer lands on its own: at the end of
the approach it selects P65, descends at 1 m/s and nulls the horizontal
velocity.

Requirements
------------
1. :req:`LGC-GDN-005`
2. :req:`LGC-GDN-006`

.. rvt::

   (Precondition "LM at low gate, crew hands off"
     (lm-ready-for? :standard :low-gate :hands-off)
     :heal "Boot a standard mission at low gate with the crew's hands off"
     (boot-for :standard :low-gate :hands-off))

Steps
-----

.. rvt:: P65 takes over

   (Wait lgc.program = 65 :within 30s)
   (RunFor 30)
   (Verify nav.altitude-rate within? -1.2 -0.8)
   (Verify (abs (Read truth.vx)) < 1)

.. rvt:: Contact ends powered descent

   (Wait contact-light :within 5min)
   (RunFor 1)
   (Verify lgc.program = 68)
   (Verify engine.descent.on = false)
   (FlyTo :touchdown)
   (Verify (landed-within-limits?))
