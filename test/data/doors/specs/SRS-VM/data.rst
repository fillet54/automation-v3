Data storage and memory
=======================

.. requirement:: VM-MEM-001
   :satisfies: SEG-SPC-010
   :subsystem: MEM
   :verification: Test
   :last-modified-by: doors-import

   The VM shall store telemetry in on-board mass memory in separate
   packet stores for housekeeping, events and payload data.

.. requirement:: VM-MEM-002
   :satisfies: SEG-SPC-010
   :subsystem: MEM
   :verification: Test
   :last-modified-by: doors-import

   The VM shall store at least 72 hours of housekeeping telemetry before a
   packet store wraps.

.. requirement:: VM-MEM-003
   :satisfies: SEG-SPC-010
   :subsystem: MEM
   :verification: Test
   :last-modified-by: doors-import

   The VM shall downlink a packet store's contents, oldest first, on
   telecommand, at up to 2 Mbit/s on the X-band link, and keep them until
   the ground confirms receipt.

.. requirement:: VM-MEM-004
   :satisfies: SEG-SPC-010
   :subsystem: MEM
   :verification: Test
   :last-modified-by: doors-import

   The VM shall scrub its EDAC-protected memory completely at least once
   every 24 hours, correcting single-bit errors and reporting double-bit
   errors as events.

.. requirement:: VM-MEM-005
   :satisfies: SEG-SPC-010
   :subsystem: MEM
   :verification: Test
   :last-modified-by: doors-import

   The VM shall accept a software image upload in segments, verify the
   complete image against its CRC, and write it to the non-active image
   slot only on a separate telecommand.

.. requirement:: VM-MEM-006
   :satisfies: SEG-SPC-010
   :subsystem: MEM
   :verification: Test
   :last-modified-by: doors-import

   The VM shall allow any memory address to be dumped and patched by
   telecommand, with a patch to code memory treated as a hazardous
   telecommand.
