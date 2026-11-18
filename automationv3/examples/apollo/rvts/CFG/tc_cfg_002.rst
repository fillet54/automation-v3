==============================
Extended Missions Are Accepted
==============================
Boots an extended mission's erasable load and flies it to high gate on
that mission's numbers.

.. note::

   Fails on LUM099, which has no extended missions (they came with
   Luminary 1E, LUM210 here).

Requirements
------------
1. :req:`LGC-CFG-002`

.. rvt::

   (import GDN)

Steps
-----

.. rvt:: The load is accepted

   (Verify (.boot lm {:mission :extended}) = :accepted)
   (Verify lgc.config.mission = :extended)
   (Verify (.get (Keys "V06N93E") :r2) = 9000)

.. rvt:: The descent flies the extended mission's approach

   (FlyTo :high-gate)
   (Verify (approach-angle-from (Read truth.downrange) (Read truth.altitude))
           within? 22.5 27.5)
