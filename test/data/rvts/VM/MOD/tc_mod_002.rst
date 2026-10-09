=============================
Autonomous Entry to SAFE Mode
=============================
Requests SAFE mode through FDIR from each mode, with an attitude error
held past its persistence time, and checks what the VM does on entering
SAFE, and that only a telecommand takes it out again.

Requirements
------------
1. :req:`VM-MOD-004`
2. :req:`VM-MOD-005`
3. :req:`VM-MOD-006`

.. rvt::

   (variations "from"
     ["from-standby"  [:standby]
      "from-nominal"  [:nominal]
      "from-maneuver" [:maneuver]])

   (Precondition "Platform in the variation's mode"
     (platform-in-mode? from)
     :heal "Command the platform to the mode"
     (command-mode from))

Steps
-----

.. rvt:: Request SAFE mode

   (def noops-before (Telemetry :noop-count))
   (Verify (SendTC :noop :at (+ (now) 600)) = :queued)
   (.inject vm :attitude-error 15.0)
   (RunFor 61)
   (Verify (Telemetry :mode) = :safe)

.. rvt:: Within 5 s of entering SAFE

   (Verify (.safe_entry_delay vm) <= safe-mode-actions-s)
   (Verify (line-on? :payload) = false)
   (Verify (Telemetry :attitude-mode) = :sun-pointing)
   (Verify (line-on? :heater-non-essential) = false)
   (Verify (Telemetry :tt-suspended))

.. rvt:: Staying in SAFE

   (.inject vm :attitude-error 0.0)
   (RunFor 600)
   (Verify (Telemetry :mode) = :safe)
   (Verify (Telemetry :noop-count) = noops-before)
   (command-mode :standby)
