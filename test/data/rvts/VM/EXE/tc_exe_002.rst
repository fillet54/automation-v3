==================
Watchdog Servicing
==================
Checks the VM services the hardware watchdog while healthy, and stops
servicing it (so the watchdog resets the processor) when a task stops
running or minor frames keep overrunning.

Requirements
------------
1. :req:`VM-EXE-003`

.. rvt::

   (variations "fault"
     ["healthy"         [:none]
      "task-stalled"    [:stall-telemetry-task]
      "repeated-overrun" [:overrun-every-frame]])

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Watch the watchdog line

   (TBD "Connect the logic analyser to the watchdog service line")
   (TBD "Verify the service interval is under watchdog-service-ms (500 ms) for 60 s")

.. rvt:: Inject the fault

   (TBD "Inject the variation's fault with the fault injection telecommand")

.. rvt-variant::
   :variations: healthy

   With no fault, servicing continues.

   .. rvt:: Still serviced

      (TBD "Verify the service interval stays under 500 ms for a further 60 s")

.. rvt-variant::
   :variations: task-stalled, repeated-overrun

   With a fault, servicing stops and the watchdog resets the processor.

   .. rvt:: Watchdog reset

      (TBD "Verify servicing stops within two periods of the stalled task, or within 10 overrun minor frames")
      (TBD "Verify the processor resets and the reset cause reads watchdog after boot")
