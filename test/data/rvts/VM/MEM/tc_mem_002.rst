==============================
Memory Scrub and Software Load
==============================
Checks EDAC scrubbing, a software image upload, and memory dump and
patch.

Requirements
------------
1. :req:`VM-MEM-004`
2. :req:`VM-MEM-005`
3. :req:`VM-MEM-006`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Scrubbing

   (TBD "Inject a single-bit error and a double-bit error at known addresses with the bench debugger")
   (TBD "Verify the scrub reaches both addresses within 24 hours")
   (TBD "Verify the single-bit error is corrected and the double-bit error is reported as an event")

.. rvt:: Software upload

   (TBD "Upload a new image in 512 byte segments, with one segment corrupted")
   (TBD "Verify the image CRC check fails and the image slot is unchanged")
   (TBD "Re-upload the corrupted segment and verify the CRC check passes")
   (TBD "Verify nothing is written to the non-active slot until the write telecommand")

.. rvt:: Dump and patch

   (TBD "Dump 256 bytes of data memory and compare with the bench debugger's read")
   (TBD "Patch 4 bytes of data memory and verify the dump shows the patch")
