Fault detection, isolation and recovery
=======================================

.. requirement:: VM-FDIR-001
   :satisfies: SEG-SPC-005
   :subsystem: FDIR
   :verification: Test
   :last-modified-by: doors-import

   The VM shall monitor each parameter in the monitoring table against its
   limits every major frame, and declare a limit violation after the
   number of consecutive out-of-limit samples defined for it.

.. requirement:: VM-FDIR-002
   :satisfies: SEG-SPC-005
   :subsystem: FDIR
   :verification: Test
   :last-modified-by: doors-import

   The VM shall execute the recovery action defined for a limit violation
   within 1 s of declaring it.

.. requirement:: VM-FDIR-003
   :satisfies: SEG-SPC-005
   :subsystem: FDIR
   :verification: Test
   :last-modified-by: doors-import

   The VM shall allow each monitor and each recovery action to be enabled
   and disabled individually by telecommand.

.. requirement:: VM-FDIR-004
   :satisfies: SEG-SPC-005
   :subsystem: FDIR
   :verification: Test
   :last-modified-by: doors-import

   The VM shall switch to the redundant unit when a unit fails, for each
   of the following:

   - transponder;
   - star tracker;
   - reaction wheel (from four to the remaining three);
   - battery charge regulator.

.. requirement:: VM-FDIR-005
   :satisfies: SEG-SPC-005
   :subsystem: FDIR
   :verification: Test
   :last-modified-by: doors-import

   The VM shall request SAFE mode if any of the following persists for
   more than its stated time:

   - attitude error greater than 10 deg, for 60 s;
   - battery state of charge below 40%, for 10 s;
   - loss of uplink, for 72 hours;
   - any FDIR recovery action that does not clear its fault, for 300 s.

.. requirement:: VM-FDIR-006
   :satisfies: SEG-SPC-005
   :subsystem: FDIR
   :verification: Test
   :last-modified-by: doors-import

   The VM shall not take the same autonomous recovery action more than
   three times within 24 hours without a telecommand acknowledging it.

.. requirement:: VM-FDIR-007
   :satisfies: SEG-SPC-005
   :subsystem: FDIR
   :verification: Test
   :last-modified-by: doors-import

   The VM shall keep a log of the last 256 fault detections and recovery
   actions in non-volatile memory.
