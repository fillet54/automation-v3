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
   (SetFixedValue bench.attitude-error 15.0)
   (Wait modes.current = :safe :within 2min)
   (ClearFixedValue bench.attitude-error)

.. rvt:: Within 5 s of entering SAFE

   (Verify (.safe_entry_delay vm) <= safe-mode-actions-s)
   (Verify lines.payload.on = false)
   (Verify modes.attitude = :sun-pointing)
   (Verify lines.heater-non-essential.on = false)
   (Verify tc.tt-suspended)
