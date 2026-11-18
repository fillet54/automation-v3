=======================
Abort From Any Altitude
=======================
Flies down from powered descent initiation and presses ABORT at each
altitude: high in the braking phase, at the start of the approach, near
low gate, and just above the surface. Each time the LM must climb away
on the descent engine. Each altitude is a variation, since an abort ends
the flight. Queue the low ones alone with ``(< abort-m 1000)``.

Requirements
------------
1. :req:`MSN-002`
2. :req:`LGC-ABT-001`

.. rvt::

   (import GDN)

   (variations "abort-m"
     ["at 12 km"  [12000]
      "at 3 km"   [3000]
      "at 300 m"  [300]
      "at 30 m"   [30]])

   (Precondition "LM at PDI"
     (lm-ready? :standard :pdi)
     :heal "Boot a standard mission at PDI"
     (boot :standard :pdi))

Steps
-----

.. rvt:: Down to the abort altitude

   (FlyTo :ignition)
   (Wait truth.altitude <= abort-m :within 15min :every 2s)

.. rvt:: ABORT

   (SetValue panel.abort true)
   (RunFor 2)
   (Verify lgc.program = 70)
   (Verify deca.throttle = full-throttle)
   (RunFor 20)
   (Verify (climbing?))
   (Verify landed = false)
