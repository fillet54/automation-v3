Electrical power
================

.. requirement:: VM-EPS-001
   :satisfies: SEG-SPC-007
   :subsystem: EPS
   :verification: Test
   :last-modified-by: doors-import

   The VM shall compute the battery state of charge every major frame from
   the battery voltage, current and temperature.

.. requirement:: VM-EPS-002
   :satisfies: SEG-SPC-007
   :subsystem: EPS
   :verification: Test
   :last-modified-by: doors-import

   The VM shall shed loads in the order of the load shedding table when
   the battery state of charge falls below each of the following
   thresholds:

   - 60%: the payload;
   - 50%: the non-essential heaters;
   - 40%: everything except the essential loads (bus computer,
     receivers, essential heaters).

.. requirement:: VM-EPS-003
   :satisfies: SEG-SPC-007
   :subsystem: EPS
   :verification: Test
   :last-modified-by: doors-import

   The VM shall restore loads shed for low state of charge only on
   telecommand.

.. requirement:: VM-EPS-004
   :satisfies: SEG-SPC-007
   :subsystem: EPS
   :verification: Test
   :last-modified-by: doors-import

   The VM shall limit battery charge current to C/5 and stop charging at a
   state of charge of 95%.

.. requirement:: VM-EPS-005
   :satisfies: SEG-SPC-007
   :subsystem: EPS
   :verification: Test
   :last-modified-by: doors-import

   The VM shall switch each power line on or off within 100 ms of the
   telecommand or autonomous action that requests it, and report its
   state and current in telemetry.

.. requirement:: VM-EPS-006
   :satisfies: SEG-SPC-007
   :subsystem: EPS
   :verification: Test
   :last-modified-by: doors-import

   The VM shall switch off a power line whose current exceeds its trip
   limit for more than 10 ms, and shall not switch it back on
   autonomously.
