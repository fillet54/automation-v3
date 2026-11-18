Alarms and the executive
========================

.. requirement:: LGC-ALM-001
   :satisfies: LM-GNC-001, LM-CWS-001
   :subsystem: ALM
   :verification: Test
   :last-modified-by: doors-import

   When the computer's work exceeds its capacity, it shall raise program alarm 1202, restart, drop the monitor display job, and keep navigating and guiding without interruption.

.. requirement:: LGC-ALM-002
   :satisfies: LM-CWS-001
   :subsystem: ALM
   :verification: Test
   :last-modified-by: doors-import

   A program alarm shall light PROG on the DSKY and the PROG caution, and sound the master alarm.

.. requirement:: LGC-EXE-001
   :satisfies: LM-GNC-001
   :subsystem: ALM
   :verification: Analysis
   :last-modified-by: doors-import

   With no monitor display, the executive's load shall stay below 85% of the computer's capacity in every descent program.
