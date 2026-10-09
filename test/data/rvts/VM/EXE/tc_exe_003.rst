==================
Watchdog Servicing
==================
Checks the VM services the hardware watchdog while healthy, and stops
when a task stalls or minor frames keep overrunning, so the watchdog
resets the processor.

Requirements
------------
1. :req:`VM-EXE-003`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Healthy

   (TBD "Connect the logic analyser to the watchdog service line")
   (TBD "Verify the service interval stays under watchdog-service-ms (500 ms) for 60 s")

.. rvt:: Each fault
   :table:

   ("fault"
     ["task stalled"      [:stall-telemetry-task]
      "repeated overrun"  [:overrun-every-frame]])

   (TBD "Inject the row's fault with the fault injection telecommand")
   (TBD "Verify servicing stops within two periods of the stalled task, or within 10 overrun minor frames")
   (TBD "Verify the processor resets and boots back into cyclic execution")
