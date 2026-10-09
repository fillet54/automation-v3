====================
Power Line Switching
====================
Switches each switchable power line off and on by telecommand and
checks each switches within 100 ms and reports its state.

Requirements
------------
1. :req:`VM-EPS-005`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Each line
   :table:

   ("line relay"
     ["star tracker"          [:star-tracker lines.star-tracker]
      "transponder B"         [:transponder-b xpdr-b]
      "payload"               [:payload lines.payload]
      "non-essential heaters" [:heater-non-essential lines.heater-non-essential]])

   (Verify (SendTC :line-off :line line) = :executed)
   (Verify relay.on = false)
   (Verify relay.switch-ms <= 100)
   (Verify (SendTC :line-on :line line) = :executed)
   (Verify relay.on)

.. rvt:: Both transponders back on

   (Verify transponders.on)
