=======================
SAFE Mode Entry Actions
=======================
Requests SAFE through FDIR from NOMINAL and checks the four things the
VM must do within 5 s of entering it.

Requirements
------------
1. :req:`VM-MOD-005`

.. rvt::

   (Precondition "Platform in NOMINAL"
     (platform-in-mode? :nominal)
     :heal "Command the platform to NOMINAL"
     (command-mode :nominal))

Steps
-----

.. rvt:: Request SAFE mode

   (Verify (SendTC :tt-resume) = :executed)
   (Verify (SendTC :noop :at (+ (now) 600)) = :queued)
   (.inject vm :attitude-error 15.0)
   (RunFor 61)
   (Verify (Telemetry :mode) = :safe)
   (.inject vm :attitude-error 0.0)

.. rvt:: Within 5 s of entering SAFE

   (Verify (.safe_entry_delay vm) <= safe-mode-actions-s)
   (Verify (line-on? :payload) = false)
   (Verify (Telemetry :attitude-mode) = :sun-pointing)
   (Verify (line-on? :heater-non-essential) = false)
   (Verify (Telemetry :tt-suspended))
