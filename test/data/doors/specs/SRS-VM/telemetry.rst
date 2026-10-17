Telemetry
=========

.. requirement:: VM-TM-001
   :satisfies: SEG-SPC-003
   :subsystem: TM
   :verification: Test
   :last-modified-by: doors-import

   The VM shall generate housekeeping telemetry as CCSDS space packets.

.. requirement:: VM-TM-002
   :satisfies: SEG-SPC-003
   :subsystem: TM
   :verification: Test
   :last-modified-by: doors-import

   The VM shall generate each housekeeping packet at its defined rate,
   selectable by telecommand from 0.1 Hz to 10 Hz, with the rates at
   power-on taken from the default telemetry table.

.. requirement:: VM-TM-003
   :satisfies: SEG-SPC-003
   :subsystem: TM
   :verification: Test
   :last-modified-by: doors-import

   The VM shall time-stamp each telemetry packet with the on-board time at
   which its data was sampled, to a resolution of 1 ms.

.. requirement:: VM-TM-004
   :satisfies: SEG-SPC-003
   :subsystem: TM
   :verification: Test
   :last-modified-by: doors-import

   The VM shall downlink real-time telemetry at 32 kbit/s on the S-band
   link when a ground station is in contact.

.. requirement:: VM-TM-005
   :satisfies: SEG-SPC-003
   :subsystem: TM
   :verification: Test
   :last-modified-by: doors-import

   The VM shall record all housekeeping telemetry to on-board storage
   whether or not a ground station is in contact.

.. requirement:: VM-TM-006
   :satisfies: SEG-SPC-003
   :subsystem: TM
   :verification: Test
   :last-modified-by: doors-import

   The VM shall generate an event packet within 1 s of each of the
   following:

   - a mode transition;
   - a telecommand rejection;
   - a fault detection or recovery action;
   - a parameter limit violation.

.. requirement:: VM-TM-007
   :satisfies: SEG-SPC-003
   :subsystem: TM
   :verification: Test
   :last-modified-by: doors-import

   The VM shall maintain a monotonic packet sequence count for each
   telemetry application, wrapping at 16383.
