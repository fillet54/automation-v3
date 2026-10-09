================
Memory Scrubbing
================
Injects single- and double-bit errors and checks the scrub corrects
the one and reports the other within 24 hours.

Requirements
------------
1. :req:`VM-MEM-004`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Each error
   :table:

   ("bits outcome"
     ["single bit" [1 :corrected]
      "double bit" [2 :reported]])

   (TBD "Inject an error of the row's bits at a known address with the bench debugger")
   (TBD "Verify the scrub reaches it within 24 hours, with the row's outcome")
