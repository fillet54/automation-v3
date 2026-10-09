====================
Parameter Monitoring
====================
Checks limit monitoring, persistence, recovery actions, enabling and
disabling them, the limit on repeated recoveries, and the fault log.

Requirements
------------
1. :req:`VM-FDIR-001`
2. :req:`VM-FDIR-002`
3. :req:`VM-FDIR-003`
4. :req:`VM-FDIR-006`
5. :req:`VM-FDIR-007`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Persistence

   (TBD "Pick the battery temperature monitor: upper limit +30 degC, persistence 3 samples, recovery: battery heater off")
   (TBD "Drive the battery temperature sensor input to +31 degC for 2 s, then back to +20 degC")
   (TBD "Verify no limit violation is declared")
   (TBD "Drive it to +31 degC for 3 s")
   (TBD "Verify a limit violation is declared after the third sample and the heater is off within 1 s")

.. rvt:: Enable and disable

   (TBD "Disable the monitor by telecommand and drive +31 degC for 10 s: verify no violation")
   (TBD "Enable the monitor, disable its recovery action, repeat: verify a violation but no action")

.. rvt:: No more than three times a day

   (TBD "Enable everything and trigger the violation four times within one hour")
   (TBD "Verify the recovery action ran three times, and the fourth is held until acknowledged by telecommand")

.. rvt:: The fault log

   (TBD "Trigger 300 detections with a test monitor")
   (TBD "Power cycle and dump the fault log: verify it holds the last 256, in order")
