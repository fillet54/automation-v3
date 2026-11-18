Navigation
==========

.. requirement:: LGC-NAV-001
   :satisfies: LM-LDG-003, LM-GNC-001
   :subsystem: NAV
   :verification: Test
   :last-modified-by: doors-import

   Navigation shall take in the landing radar's altitude, then its velocity, only after the crew enables it with V57, and only while the radar reports its data good.

.. requirement:: LGC-NAV-002
   :satisfies: LM-GNC-002
   :subsystem: NAV
   :verification: Test
   :last-modified-by: doors-import

   N68 shall show the slant range to the landing site, the time to go in the phase, and the radar altitude less the computed altitude (delta-H).
