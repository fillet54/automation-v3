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

   ("line"
     ["star tracker"          [:star-tracker]
      "transponder B"         [:transponder-b]
      "payload"               [:payload]
      "non-essential heaters" [:heater-non-essential]])

   (Verify (SendTC :line-off :line line) = :executed)
   (Verify (line-on? line) = false)
   (Verify (.get (Telemetry :line line) :switch_ms) <= 100)
   (Verify (SendTC :line-on :line line) = :executed)
   (Verify (line-on? line))
