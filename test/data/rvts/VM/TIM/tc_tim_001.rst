=============
On-Board Time
=============
Checks the time format, GNSS synchronisation, free-running propagation,
time setting by telecommand, and time across a reset.

Requirements
------------
1. :req:`VM-TIM-001`
2. :req:`VM-TIM-002`
3. :req:`VM-TIM-003`
4. :req:`VM-TIM-004`
5. :req:`VM-TIM-005`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Format and synchronisation

   (TBD "Give the GNSS simulator a valid fix and its pulse per second")
   (TBD "Verify on-board time counts from 2000-01-01T12:00:00 TAI with 1 microsecond resolution")
   (TBD "Verify on-board time is within 10 microseconds of the pulse per second edge")

.. rvt:: Without GNSS

   (TBD "Remove the GNSS fix for 6 hours")
   (TBD "Verify the time since last synchronisation in telemetry grows from 0 to 6 hours")
   (TBD "Restore the fix and verify resynchronisation")

.. rvt:: Setting time

   (TBD "Adjust time by 0.5 s by telecommand: verify it is applied")
   (TBD "Load a time-tagged NO-OP due in 30 s, then command a 2 s adjustment: verify it is rejected")

.. rvt:: Across a reset

   (TBD "Command a processor reset")
   (TBD "Verify on-board time after boot differs from the GNSS reference by less than 1 ms")
