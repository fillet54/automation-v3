===========
Engine Stop
===========
Holds ENGINE STOP in the approach and checks the descent engine stays
off whatever guidance asks for, then lets go and checks it relights.

Requirements
------------
1. :req:`LM-ABT-002`

.. rvt::

   (Precondition "LM at high gate"
     (lm-ready? :standard :high-gate)
     :heal "Boot a standard mission at high gate"
     (boot :standard :high-gate))

Steps
-----

.. rvt:: ENGINE STOP held

   (SetFixedValue panel.engine-stop true)
   (quietly (RunFor 3))
   (Verify engine.descent.on = false)
   (Verify deca.throttle = 0)
   (if (try-ok? (Verify lgc.program = 64))
     (Verify (Read lgc.program) = 64)
     (Verify (Read lgc.program) = 65))

.. rvt:: Let go

   (ClearFixedValue panel.engine-stop)
   (SetValue panel.engine-stop false)
   (RunFor 1)
   (Verify engine.descent.on = true)
