Executive
=========

.. requirement:: VM-EXE-001
   :satisfies: SEG-SPC-001
   :subsystem: EXE
   :verification: Test
   :last-modified-by: doors-import

   The VM shall execute its scheduled tasks in a fixed cyclic schedule
   with a major frame of 1 s divided into 10 minor frames of 100 ms.

.. requirement:: VM-EXE-002
   :satisfies: SEG-SPC-001
   :subsystem: EXE
   :verification: Test
   :last-modified-by: doors-import

   The VM shall complete every task scheduled in a minor frame before the
   start of the next minor frame. A minor frame overrun shall be counted
   in telemetry and reported as an event.

.. requirement:: VM-EXE-003
   :satisfies: SEG-SPC-001
   :subsystem: EXE
   :verification: Test
   :last-modified-by: doors-import

   The VM shall service the hardware watchdog at least once every 500 ms
   while all of the following hold:

   - every scheduled task has run within its last two scheduled periods;
   - no minor frame overrun has occurred in the last 10 consecutive minor
     frames.

.. requirement:: VM-EXE-004
   :satisfies: SEG-SPC-001
   :subsystem: EXE
   :verification: Test
   :last-modified-by: doors-import

   On power-on or processor reset, the VM shall complete its boot sequence
   and begin cyclic execution within 20 s.

.. requirement:: VM-EXE-005
   :satisfies: SEG-SPC-001
   :subsystem: EXE
   :verification: Test
   :last-modified-by: doors-import

   The VM shall record the cause of each processor reset (power-on,
   watchdog, commanded, or exception) in non-volatile memory, and report
   it in telemetry after the next boot.

.. requirement:: VM-EXE-006
   :satisfies: SEG-SPC-001
   :subsystem: EXE
   :verification: Test
   :last-modified-by: doors-import

   The VM shall boot from the primary software image unless one of the
   following holds, in which case it shall boot from the backup image:

   - the primary image fails its integrity check;
   - three consecutive resets have occurred, each within 60 s of boot.

.. requirement:: VM-EXE-007
   :satisfies: SEG-SPC-001
   :subsystem: EXE
   :verification: Test
   :last-modified-by: doors-import

   The VM shall not use more than 70% of the processor's capacity,
   averaged over any major frame, in any mode.
