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

   (Verify (SendTC :auth-enable :key 42) = :executed)

.. rvt:: Send through transponder A

   (def count-before (Telemetry :noop-count))
   (Verify (SendTC :noop :defect defect :via :a) = expected-result)
   (Verify (Telemetry :last-report-latency) <= tc-report-limit-s)
   (Verify (Telemetry :noop-count)
           = (if (= expected-result :executed) (+ count-before 1) count-before))

.. rvt:: Send through transponder B

   (Verify (SendTC :noop :defect defect :via :b) = expected-result)

.. rvt:: Order of execution

   (step "Five NO-OPs, numbered"
     (SendTC :noop :seq 1)
     (SendTC :noop :seq 2)
     (SendTC :noop :seq 3)
     (SendTC :noop :seq 4)
     (SendTC :noop :seq 5))
   (Verify (.report_seqs vm 5) = [1 2 3 4 5])
