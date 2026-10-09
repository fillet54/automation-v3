==================
Housekeeping Rates
==================
Checks the default rates after power-on, then sets a packet's rate to
the slowest, default and fastest rates and measures each.

Requirements
------------
1. :req:`VM-TM-002`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Defaults after power-on

   (power-cycle-bus-computer)
   (TBD "Verify each housekeeping packet's rate matches the default telemetry table within 1%")

.. rvt:: Each rate
   :table:

   ("rate-hz"
     ["slowest" [0.1]
      "default" [1.0]
      "fastest" [10.0]])

   (TBD "Command the power housekeeping packet to rate-hz")
   (TBD "Record its packets for 100 / rate-hz seconds and verify the rate is rate-hz within 1%")
