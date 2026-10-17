Mode management
===============

.. requirement:: VM-MOD-001
   :satisfies: SEG-SPC-004
   :subsystem: MOD
   :verification: Test
   :last-modified-by: doors-import

   The VM shall operate the platform in exactly one of the following
   modes at a time:

   - LAUNCH: from separation until the first commanded transition;
   - SAFE: Sun-pointing, minimum power, payload off;
   - STANDBY: nominal attitude, payload off;
   - NOMINAL: payload operations;
   - MANEUVER: orbit control with propulsion.

.. requirement:: VM-MOD-002
   :satisfies: SEG-SPC-004
   :subsystem: MOD
   :verification: Test
   :last-modified-by: doors-import

   The VM shall enter LAUNCH mode on its first boot after separation is
   detected, and shall remain in LAUNCH mode for at least 30 minutes.

.. requirement:: VM-MOD-003
   :satisfies: SEG-SPC-004
   :subsystem: MOD
   :verification: Test
   :last-modified-by: doors-import

   The VM shall make only the following mode transitions on telecommand:

   - LAUNCH to SAFE;
   - SAFE to STANDBY;
   - STANDBY to NOMINAL, STANDBY to MANEUVER and STANDBY to SAFE;
   - NOMINAL to STANDBY and NOMINAL to SAFE;
   - MANEUVER to STANDBY and MANEUVER to SAFE.

   Any other commanded transition shall be rejected.

.. requirement:: VM-MOD-004
   :satisfies: SEG-SPC-004
   :subsystem: MOD
   :verification: Test
   :last-modified-by: doors-import

   The VM shall transition to SAFE mode autonomously, from any mode other
   than LAUNCH, when FDIR requests it.

.. requirement:: VM-MOD-005
   :satisfies: SEG-SPC-004
   :subsystem: MOD
   :verification: Test
   :last-modified-by: doors-import

   On entering SAFE mode, the VM shall within 5 s:

   - command the payload off;
   - command the AOCS to Sun-pointing;
   - shed the non-essential loads;
   - suspend the time-tagged telecommand queue.

.. requirement:: VM-MOD-006
   :satisfies: SEG-SPC-004
   :subsystem: MOD
   :verification: Test
   :last-modified-by: doors-import

   The VM shall leave SAFE mode only on telecommand.

.. requirement:: VM-MOD-007
   :satisfies: SEG-SPC-004
   :subsystem: MOD
   :verification: Test
   :last-modified-by: doors-import

   The VM shall restore the mode it was in before a processor reset,
   except that it shall enter SAFE mode if the reset was caused by the
   watchdog or an exception.
