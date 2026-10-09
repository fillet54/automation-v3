================================
Acceptance and Rejection Reports
================================
Sends a valid NO-OP and one with each kind of defect, and checks every
one is reported within 2 s, each rejection with its reason as an event.

Requirements
------------
1. :req:`VM-TC-003`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Enable authentication

   (Verify (SendTC :auth-enable :key 42) = :executed)

.. rvt:: Each telecommand
   :table:

   ("defect"
     ["valid"             [:none]
      "bad CRC"           [:crc]
      "short packet"      [:length]
      "argument too high" [:argument]
      "unauthenticated"   [:authentication]])

   (SendTC :noop :defect defect)
   (Verify (Telemetry :last-report-latency) <= tc-report-limit-s)
   (if (not= defect :none)
     (Verify (Telemetry :last-event) = :tc-rejection))
