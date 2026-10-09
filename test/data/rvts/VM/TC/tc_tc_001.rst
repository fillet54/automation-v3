======================
Telecommand Validation
======================
Sends one valid telecommand and one with each kind of defect, on each
transponder, and checks that only the valid one executes and that every
rejection is reported with its reason, in order, within 2 s.

Requirements
------------
1. :req:`VM-TC-001`
2. :req:`VM-TC-002`
3. :req:`VM-TC-003`
4. :req:`VM-TC-004`

.. rvt::

   (variations "defect expected-result"
     ["valid"             [:none :executed]
      "bad-crc"           [:crc :rejected-crc]
      "short-packet"      [:length :rejected-length]
      "argument-too-high" [:argument :rejected-range]
      "unauthenticated"   [:authentication :rejected-authentication]])

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Enable authentication

   (TBD "Enable command authentication and load the test key")

.. rvt:: Send through transponder A

   (TBD "Send a NO-OP telecommand with the variation's defect through transponder A")
   (TBD "Verify the result is expected-result, reported within tc-report-limit-s (2 s)")
   (TBD "Verify the NO-OP counter incremented only if expected-result is executed")

.. rvt:: Send through transponder B

   (TBD "Repeat through transponder B and verify the same result")

.. rvt:: Order of execution

   (TBD "Send five valid NO-OP telecommands with sequence numbers 1 to 5 in one uplink frame")
   (TBD "Verify their acceptance reports appear in order 1 to 5")
