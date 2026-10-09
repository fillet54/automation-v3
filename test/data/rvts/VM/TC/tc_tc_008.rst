=========================
Hardware-Decoded Commands
=========================
Stops the VM's own telecommand processing and checks the
hardware-decoded safe-mode and reset commands still work.

Requirements
------------
1. :req:`VM-TC-008`

.. rvt::

   (Precondition "Platform in NOMINAL"
     (platform-in-mode? :nominal)
     :heal "Command the platform to NOMINAL"
     (command-mode :nominal))

Steps
-----

.. rvt:: Telecommand processing stopped

   (.stop_tc_task vm)
   (Verify (SendTC :noop) = :lost)

.. rvt:: Safe mode

   (.hw_command vm :safe)
   (Verify (Telemetry :safe-discrete))
   (Verify (Telemetry :mode) = :safe)

.. rvt:: Reset

   (.hw_command vm :reset)
   (Verify (Telemetry :reset-cause) = :commanded)
