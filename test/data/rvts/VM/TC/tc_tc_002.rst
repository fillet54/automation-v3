======================
Telecommand Validation
======================
Sends a valid NO-OP and one with each kind of defect, with command
authentication enabled, and checks only the valid one executes.

Requirements
------------
1. :req:`VM-TC-002`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Enable authentication

   (Verify (SendTC :auth-enable :key 42) = :executed)

.. rvt:: Each defect
   :table:

   ("defect expected-result"
     ["valid"             [:none :executed]
      "bad CRC"           [:crc :rejected-crc]
      "short packet"      [:length :rejected-length]
      "argument too high" [:argument :rejected-range]
      "unauthenticated"   [:authentication :rejected-authentication]])

   (let [before (Telemetry :noop-count)]
     (Verify (SendTC :noop :defect defect) = expected-result)
     (Verify (Telemetry :noop-count)
             = (if (= expected-result :executed) (+ before 1) before)))
