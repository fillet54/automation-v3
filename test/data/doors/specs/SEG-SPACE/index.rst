Space Segment Specification
===========================

The space segment is the satellite: its platform and its on-board software.
Each requirement here traces up to the mission system specification.

Platform
--------

.. requirement:: SEG-SPC-001
   :satisfies: SYS-003
   :verification: Test

   The spacecraft's on-board software shall execute deterministically, recovering from processor resets autonomously.

.. requirement:: SEG-SPC-002
   :satisfies: SYS-002
   :verification: Test

   The spacecraft shall accept authenticated telecommands, immediate and time-tagged, and acknowledge each.

.. requirement:: SEG-SPC-003
   :satisfies: SYS-002
   :verification: Test

   The spacecraft shall downlink housekeeping telemetry continuously while in contact and store it otherwise.

.. requirement:: SEG-SPC-004
   :satisfies: SYS-003
   :verification: Test

   The spacecraft shall have a safe mode, entered autonomously or by command, in which it survives indefinitely.

.. requirement:: SEG-SPC-005
   :satisfies: SYS-003
   :verification: Test

   The spacecraft shall detect, isolate and recover from single failures without loss of the mission.

.. requirement:: SEG-SPC-006
   :satisfies: SYS-001
   :verification: Test

   The spacecraft shall point its imager at a commanded target to within 0.1° and hold it for 30 s.

.. requirement:: SEG-SPC-007
   :satisfies: SYS-004
   :verification: Test

   The spacecraft shall manage its power so that the battery state of charge never falls below 30%.

.. requirement:: SEG-SPC-008
   :satisfies: SYS-004
   :verification: Test

   The spacecraft shall keep every unit within its operational temperature range in every mode.

.. requirement:: SEG-SPC-009
   :satisfies: SYS-006
   :verification: Test

   The spacecraft shall keep on-board time within 1 ms of UTC, correlated by the ground.

.. requirement:: SEG-SPC-010
   :satisfies: SYS-006
   :verification: Test

   The spacecraft shall store at least 72 h of telemetry and event history in non-volatile memory.
