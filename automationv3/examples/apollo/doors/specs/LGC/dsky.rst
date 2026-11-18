Display and keyboard
====================

.. requirement:: LGC-DSK-001
   :satisfies: MSN-003
   :subsystem: DSK
   :verification: Test
   :last-modified-by: doors-import

   V35 shall light every DSKY light for five seconds.

.. requirement:: LGC-DSK-002
   :satisfies: MSN-003
   :subsystem: DSK
   :verification: Test
   :last-modified-by: doors-import

   An unknown verb or noun, or an entry incomplete at ENTR, shall light OPR ERR; RSET shall put it out.

.. requirement:: LGC-DSK-003
   :satisfies: MSN-003
   :subsystem: DSK
   :verification: Test
   :last-modified-by: doors-import

   V16 shall show a noun and update it every two-second guidance cycle; V06 shall show the values of the moment it was keyed.

.. requirement:: LGC-DSK-004
   :satisfies: MSN-003
   :subsystem: DSK
   :verification: Test
   :last-modified-by: doors-import

   When a program wants the display while the crew is monitoring with V16, KEY REL shall light; the KEY REL key shall give the display to the program.

.. requirement:: LGC-DSK-005
   :satisfies: MSN-003
   :subsystem: DSK
   :verification: Test
   :last-modified-by: doors-import

   V05 N09 shall show the last three program alarm codes.
