=============================
Autonomous Entry to SAFE Mode
=============================
Requests SAFE mode through FDIR from each mode and checks what the VM
does on entering it, and that only a telecommand takes it out again.

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

   (TBD "Load a time-tagged NO-OP for 10 minutes from now")
   (TBD "Force an FDIR SAFE request by injecting a 15 deg attitude error for 61 s")
   (TBD "Verify the mode becomes SAFE")

.. rvt:: Within 5 s of entering SAFE

   (TBD "Verify the payload power line is off")
   (TBD "Verify the AOCS reports Sun-pointing as its commanded mode")
   (TBD "Verify the non-essential loads are off")
   (TBD "Verify the time-tagged queue reports suspended")

.. rvt:: Staying in SAFE

   (TBD "Clear the injected attitude error and wait 10 minutes")
   (TBD "Verify the mode is still SAFE and the time-tagged NO-OP did not execute")
   (command-mode :standby)
   (TBD "Verify the mode is STANDBY")
