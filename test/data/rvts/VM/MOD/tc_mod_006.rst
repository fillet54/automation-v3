=================
Leaving SAFE Mode
=================
Clears the fault that put the platform in SAFE, waits, and checks it
stays in SAFE until commanded out.

Requirements
------------
1. :req:`VM-MOD-006`

.. rvt::

   (Precondition "Platform in SAFE"
     (platform-in-mode? :safe)
     :heal "Command the platform to SAFE"
     (command-mode :safe))

Steps
-----

.. rvt:: No way out but a telecommand

   (.inject vm :attitude-error 0.0)
   (.set_battery vm 80.0)
   (RunFor 600)
   (Verify (Telemetry :mode) = :safe)

.. rvt:: Commanded out

   (Verify (SendTC :set-mode :mode :standby) = :executed)
   (Verify (Telemetry :mode) = :standby)
