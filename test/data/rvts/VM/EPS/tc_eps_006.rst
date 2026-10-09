================
Overcurrent Trip
================
Overloads the star tracker line briefly and then for longer than 10 ms,
and checks it trips only the second time and stays off.

Requirements
------------
1. :req:`VM-EPS-006`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: A known state

   (Verify (SendTC :line-on :line :star-tracker) = :executed)

.. rvt:: Shorter than 10 ms

   (.overload vm :star-tracker 1.2 5)
   (Verify (line-on? :star-tracker))

.. rvt:: Longer than 10 ms

   (.overload vm :star-tracker 1.2 15)
   (Verify (line-on? :star-tracker) = false)
   (Verify (.get (Telemetry :line :star-tracker) :tripped))
   (RunFor 60)
   (Verify (line-on? :star-tracker) = false)
