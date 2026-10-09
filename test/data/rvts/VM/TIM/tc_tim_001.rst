===========
Time Format
===========
Checks on-board time counts from the J2000 TAI epoch with 1
microsecond resolution.

Requirements
------------
1. :req:`VM-TIM-001`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Format

   (TBD "Set on-board time to a known TAI instant and verify the seconds and subseconds fields")
