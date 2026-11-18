Descent programs
================

.. requirement:: LGC-GDN-001
   :satisfies: LM-GNC-001, LM-GNC-002
   :subsystem: GDN
   :verification: Test
   :last-modified-by: doors-import

   At powered descent initiation, P63 shall flash V99 N62 and light the descent engine only after the crew presses PRO.

.. requirement:: LGC-GDN-002
   :satisfies: LM-PRP-001
   :subsystem: GDN
   :verification: Test
   :last-modified-by: doors-import

   P63 shall brake at full throttle until the thrust it needs falls below 57%, then throttle down, and stay within the throttling range for the rest of the descent.

.. requirement:: LGC-GDN-003
   :satisfies: LM-GNC-001
   :subsystem: GDN
   :verification: Test
   :last-modified-by: doors-import

   P63 shall hand over to P64 at high gate; P64 shall fly to low gate along the approach angle the erasable load gives.

.. requirement:: LGC-GDN-004
   :satisfies: LM-GNC-001, LM-LDG-001
   :subsystem: GDN
   :verification: Test
   :last-modified-by: doors-import

   In P64 or P65 the first click of the rate-of-descent switch shall select P66; in P66 each further click shall change the commanded rate of descent by 1 ft/s, and P66 shall hold that rate with the throttle.

.. requirement:: LGC-GDN-005
   :satisfies: LM-LDG-001
   :subsystem: GDN
   :verification: Test
   :last-modified-by: doors-import

   If the crew has not selected P66 by low gate, P65 shall descend vertically at 1 m/s, nulling the horizontal velocity.

.. requirement:: LGC-GDN-006
   :satisfies: LM-LDG-002
   :subsystem: GDN
   :verification: Test
   :last-modified-by: doors-import

   The lunar contact light shall end powered descent: P68 shall command no further thrust.

.. requirement:: LGC-ABT-001
   :satisfies: LM-ABT-003
   :subsystem: ABT
   :verification: Test
   :last-modified-by: doors-import

   ABORT shall, at any time before landing, select P70: full thrust, upright, climbing.

.. requirement:: LGC-ABT-002
   :satisfies: LM-GNC-002
   :subsystem: ABT
   :verification: Test
   :last-modified-by: doors-import

   V37 shall select P00 only once landed, and P70 or P71 only before landing; any other program change shall light OPR ERR.
