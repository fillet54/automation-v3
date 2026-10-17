Telecommand
===========

.. requirement:: VM-TC-001
   :satisfies: SEG-SPC-002
   :subsystem: TC
   :verification: Test
   :last-modified-by: doors-import

   The VM shall accept telecommands as CCSDS space packets received from
   either transponder.

.. requirement:: VM-TC-002
   :satisfies: SEG-SPC-002
   :subsystem: TC
   :verification: Test
   :last-modified-by: doors-import

   The VM shall reject a telecommand, without executing it, if any of the
   following checks fails:

   - the packet's CRC;
   - the packet length against the length defined for its command code;
   - every argument against the range defined for it;
   - the command's authentication, when command authentication is
     enabled.

.. requirement:: VM-TC-003
   :satisfies: SEG-SPC-002
   :subsystem: TC
   :verification: Test
   :last-modified-by: doors-import

   The VM shall report the acceptance or rejection of every telecommand
   in telemetry within 2 s of its receipt, with the reason for any
   rejection.

.. requirement:: VM-TC-004
   :satisfies: SEG-SPC-002
   :subsystem: TC
   :verification: Test
   :last-modified-by: doors-import

   The VM shall execute accepted telecommands in the order they were
   received.

.. requirement:: VM-TC-005
   :satisfies: SEG-SPC-002
   :subsystem: TC
   :verification: Test
   :last-modified-by: doors-import

   The VM shall store up to 1000 time-tagged telecommands and execute
   each within 1 s of its time tag.

.. requirement:: VM-TC-006
   :satisfies: SEG-SPC-002
   :subsystem: TC
   :verification: Test
   :last-modified-by: doors-import

   The VM shall discard a time-tagged telecommand whose time tag is more
   than 10 s in the past when it is received, and report it as rejected.

.. requirement:: VM-TC-007
   :satisfies: SEG-SPC-002
   :subsystem: TC
   :verification: Test
   :last-modified-by: doors-import

   The VM shall require a hazardous telecommand to be preceded, within
   30 s, by an arm telecommand for the same command code, and shall
   reject it otherwise. The hazardous telecommands include:

   - propulsion valve open;
   - deployment actuator fire;
   - software image overwrite.

.. requirement:: VM-TC-008
   :satisfies: SEG-SPC-002
   :subsystem: TC
   :verification: Test
   :last-modified-by: doors-import

   The VM shall execute the hardware-decoded reset and safe-mode commands
   independently of the VM's own telecommand processing.
