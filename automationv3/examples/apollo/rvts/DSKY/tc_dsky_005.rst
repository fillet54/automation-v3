==============================
Key Release, Written Too Late
==============================
Meant to check KEY REL; its precondition comes after a step.

.. warning::

   Refuses to queue on purpose: preconditions must come before the first
   step. The editor shows the error, and the queue dialog lists the
   script as skipped.

Requirements
------------
1. :req:`LGC-DSK-004`

.. rvt::

   (Keys "V16N68E")

   (Precondition "Too late to matter"
     (lm-ready? :standard :high-gate))
