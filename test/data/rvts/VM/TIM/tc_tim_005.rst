===================
Time Across a Reset
===================
Resets the processor and checks on-board time is kept to within 1 ms.

Requirements
------------
1. :req:`VM-TIM-005`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Command a processor reset

   (TBD)

.. rvt:: Verify on-board time after boot differs from the GNSS reference by less than 1 ms

   (TBD)
