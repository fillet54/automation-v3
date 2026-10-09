========================
Time-Tagged Telecommands
========================
Fills the time-tagged queue, checks each command executes within 1 s of
its time tag, and that a stale time tag is rejected.

Requirements
------------
1. :req:`VM-TC-005`
2. :req:`VM-TC-006`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Fill the queue

   (TBD "Clear the time-tagged queue")
   (TBD "Upload time-tag-capacity (1000) NO-OP telecommands tagged 1 s apart, starting 60 s from now")
   (TBD "Verify all 1000 are accepted and the queue reports full")
   (TBD "Upload one more and verify it is rejected as queue full")

.. rvt:: Execution times

   (TBD "Wait for the queue to empty, recording each NO-OP's execution time from its event packet")
   (TBD "Verify every NO-OP executed within 1 s of its time tag")

.. rvt:: A stale time tag

   (TBD "Upload a NO-OP tagged stale-time-tag-s + 1 (11 s) in the past")
   (TBD "Verify it is rejected and does not execute")
   (TBD "Upload a NO-OP tagged 9 s in the past and verify it executes at once")
