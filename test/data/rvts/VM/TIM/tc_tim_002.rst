====================
GNSS Synchronisation
====================
Gives the GNSS receiver a fix and checks on-board time follows its
pulse per second.

Requirements
------------
1. :req:`VM-TIM-002`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Synchronise

   (TBD "Give the GNSS simulator a valid fix and its pulse per second")
   (TBD "Verify on-board time is within 10 microseconds of the pulse per second edge")
