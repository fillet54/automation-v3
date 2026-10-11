=====================
Software Image Upload
=====================
Uploads a software image with a corrupted segment, then a good one, and
checks the CRC check and that nothing is written until commanded.

Requirements
------------
1. :req:`VM-MEM-005`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Upload a new image in 512 byte segments, with one segment corrupted

   (TBD)

.. rvt:: Verify the image CRC check fails and the image slot is unchanged

   (TBD)

.. rvt:: Re-upload the corrupted segment and verify the CRC check passes

   (TBD)

.. rvt:: Verify nothing is written to the non-active slot until the write telecommand

   (TBD)
