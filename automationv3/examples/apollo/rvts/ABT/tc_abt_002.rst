===========
Abort Stage
===========
Presses ABORT STAGE at high gate: with MASTER ARM off nothing happens;
with it on, the ascent stage separates and climbs on its own engine.

Requirements
------------
1. :req:`LM-ABT-001`

.. rvt::

   (import GDN)

   (Precondition "LM at high gate"
     (lm-ready? :standard :high-gate)
     :heal "Boot a standard mission at high gate"
     (boot :standard :high-gate))

Steps
-----

.. rvt:: Not without MASTER ARM

   (SetValue panel.master-arm false)
   (SetValue panel.abort-stage true)
   (RunFor 2)
   (Verify staged = false)
   (Verify lgc.program = 64)

.. rvt:: With MASTER ARM, staging and the ascent engine

   (SetValue panel.master-arm true)
   (RunFor 2)
   (Verify staged = true)
   (Verify lgc.program = 71)
   (Verify engine.ascent.on = true)
   (Verify engine.descent.on = false)
   (Wait (climbing?) :within 1min)
