Time management
===============

.. requirement:: VM-TIM-001
   :satisfies: SEG-SPC-009
   :subsystem: TIM
   :verification: Test
   :last-modified-by: doors-import

   The VM shall maintain on-board time as seconds and subseconds since
   2000-01-01T12:00:00 TAI, with a resolution of 1 microsecond.

.. requirement:: VM-TIM-002
   :satisfies: SEG-SPC-009
   :subsystem: TIM
   :verification: Test
   :last-modified-by: doors-import

   The VM shall synchronise on-board time to the GNSS receiver's pulse per
   second when the receiver reports a valid fix, to within 10
   microseconds.

.. requirement:: VM-TIM-003
   :satisfies: SEG-SPC-009
   :subsystem: TIM
   :verification: Test
   :last-modified-by: doors-import

   Without a valid GNSS fix, the VM shall propagate on-board time from its
   oscillator, and report the time since the last synchronisation in
   telemetry.

.. requirement:: VM-TIM-004
   :satisfies: SEG-SPC-009
   :subsystem: TIM
   :verification: Test
   :last-modified-by: doors-import

   The VM shall allow on-board time to be set and adjusted by telecommand,
   and shall reject a time adjustment of more than 1 s while a time-tagged
   telecommand is due within the next 60 s.

.. requirement:: VM-TIM-005
   :satisfies: SEG-SPC-009
   :subsystem: TIM
   :verification: Test
   :last-modified-by: doors-import

   The VM shall preserve on-board time across a processor reset with an
   error of less than 1 ms.
