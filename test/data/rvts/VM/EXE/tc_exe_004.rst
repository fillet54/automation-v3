=========
Boot Time
=========
Power cycles and resets the bus computer and checks cyclic execution
starts within 20 s each time.

Requirements
------------
1. :req:`VM-EXE-004`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Each kind of reset
   :table:

   ("cause"
     ["power-on"  [:power-on]
      "commanded" [:commanded]
      "watchdog"  [:watchdog]])

   (TBD "Cause the row's reset and record the time to the first housekeeping packet")
   (TBD "Verify cyclic execution began within boot-time-limit-s (20 s)")
