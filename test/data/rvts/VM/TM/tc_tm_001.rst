======================
Housekeeping Telemetry
======================
Checks housekeeping packets come out at their rates, with time stamps and
sequence counts, and that rates can be changed by telecommand.

Requirements
------------
1. :req:`VM-TM-001`
2. :req:`VM-TM-002`
3. :req:`VM-TM-003`
4. :req:`VM-TM-007`

.. rvt::

   (variations "rate-hz"
     ["slowest" [0.1]
      "default" [1.0]
      "fastest" [10.0]])

Steps
-----

.. rvt:: Sequence counts wrap as specified

   (Verify (next-sequence-count 0) = 1)
   (Verify (next-sequence-count max-sequence-count) = 0)

.. rvt:: Defaults after power-on

   (power-cycle-bus-computer)
   (TBD "Verify each housekeeping packet's rate matches the default telemetry table within 1%")

.. rvt:: Set the rate

   (TBD "Command the power housekeeping packet to rate-hz")
   (TBD "Record its packets for 100 / rate-hz seconds")
   (TBD "Verify the measured rate is rate-hz within 1%")
   (TBD "Verify each packet's time stamp is within 1 ms of the bench's record of its sampling time")
   (TBD "Verify sequence counts increase by one each packet, with no gaps")

.. rvt-variant::
   :variations: fastest

   At 10 Hz the sequence count wraps in about 27 minutes.

   .. rvt:: Wrap

      (TBD "Record until the count reaches max-sequence-count, then verify the next packet's count is 0")
