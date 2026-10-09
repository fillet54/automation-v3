========================
Charging and Power Lines
========================
Checks the battery charge current limit and end of charge, power line
switching times, and the overcurrent trip.

Requirements
------------
1. :req:`VM-EPS-004`
2. :req:`VM-EPS-005`
3. :req:`VM-EPS-006`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Charging

   (TBD "Set the battery simulator to 50% and the solar array simulator to full sunlight")
   (TBD "Verify charge current never exceeds C/5")
   (TBD "Verify charging stops at 95% state of charge")

.. rvt:: Switching

   (TBD "Switch each power line on and off by telecommand")
   (TBD "Verify each switches within 100 ms, and telemetry reports its state and current")

.. rvt:: Overcurrent trip

   (TBD "Draw 120% of the star tracker line's trip limit for 5 ms: verify the line stays on")
   (TBD "Draw it for 15 ms: verify the line switches off")
   (TBD "Remove the overload and wait 60 s: verify the line stays off")
