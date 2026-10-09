=====================
Memory Dump and Patch
=====================
Dumps and patches data memory by telecommand, and checks a patch to
code memory is treated as a hazardous telecommand.

Requirements
------------
1. :req:`VM-MEM-006`

.. rvt::

   (Precondition "Platform in MANEUVER"
     (platform-in-mode? :maneuver)
     :heal "Command the platform to MANEUVER"
     (command-mode :maneuver))

Steps
-----

.. rvt:: Dump and patch data memory

   (TBD "Dump 256 bytes of data memory and compare with the bench debugger's read")
   (TBD "Patch 4 bytes of data memory and verify the dump shows the patch")

.. rvt:: Code memory patches are hazardous
   :table:

   ("armed expected-result"
     ["unarmed" [false :rejected-not-armed]
      "armed"   [true :executed]])

   (if armed (Verify (SendTC :arm :command :code-memory-patch) = :executed))
   (Verify (SendTC :code-memory-patch) = expected-result)
