=================
Time-Tagged Queue
=================
Fills the time-tagged queue to its capacity, checks it refuses one
more, and that every queued command executes within 1 s of its time
tag.

Requirements
------------
1. :req:`VM-TC-005`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Fill the queue

   (Verify (SendTC :tt-clear) = :executed)
   (Verify (SendTC :tt-resume) = :executed)
   (Verify (.upload_noops vm time-tag-capacity 60 1) = time-tag-capacity)
   (Verify (Telemetry :tt-queue-count) = time-tag-capacity)
   (Verify (SendTC :noop :at (+ (now) 2000)) = :rejected-queue-full)

.. rvt:: Execution times

   (def count-before (Telemetry :noop-count))
   (RunFor (+ 60 time-tag-capacity 5))
   (Verify (Telemetry :tt-queue-count) = 0)
   (Verify (Telemetry :noop-count) = (+ count-before time-tag-capacity))
   (Verify (.max_tt_lateness vm) <= 1)
