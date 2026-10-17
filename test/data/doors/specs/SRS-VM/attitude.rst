Attitude and orbit control interface
====================================

.. requirement:: VM-AOCS-001
   :satisfies: SEG-SPC-006
   :subsystem: AOCS
   :verification: Test
   :last-modified-by: doors-import

   The VM shall run the AOCS control task at 10 Hz in every mode.

.. requirement:: VM-AOCS-002
   :satisfies: SEG-SPC-006
   :subsystem: AOCS
   :verification: Test
   :last-modified-by: doors-import

   The VM shall command the AOCS to the attitude mode required by the
   platform mode:

   - Sun-pointing in LAUNCH (after rate damping) and SAFE;
   - Nadir-pointing in STANDBY and NOMINAL;
   - the commanded inertial attitude in MANEUVER.

.. requirement:: VM-AOCS-003
   :satisfies: SEG-SPC-006
   :subsystem: AOCS
   :verification: Test
   :last-modified-by: doors-import

   In LAUNCH mode, the VM shall command rate damping until the body rates
   are below 0.5 deg/s on every axis for 60 s, then Sun acquisition.

.. requirement:: VM-AOCS-004
   :satisfies: SEG-SPC-006
   :subsystem: AOCS
   :verification: Test
   :last-modified-by: doors-import

   The VM shall enable propulsion only in MANEUVER mode.

.. requirement:: VM-AOCS-005
   :satisfies: SEG-SPC-006
   :subsystem: AOCS
   :verification: Test
   :last-modified-by: doors-import

   The VM shall end a thruster burn when the commanded delta-v is reached,
   or when the burn duration exceeds the commanded duration by 10%,
   whichever comes first.

.. requirement:: VM-AOCS-006
   :satisfies: SEG-SPC-006
   :subsystem: AOCS
   :verification: Test
   :last-modified-by: doors-import

   The VM shall unload reaction wheel momentum with the magnetorquers when
   the momentum of any wheel exceeds 80% of its capacity.
