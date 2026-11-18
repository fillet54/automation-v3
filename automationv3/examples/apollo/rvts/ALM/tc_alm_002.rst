========================
Master Alarm And Caution
========================
On the surface, fails a descent battery from the bench: the BATTERY
caution lights and the master alarm sounds until the crew pushes it;
the caution stays while the fault lasts.

Requirements
------------
1. :req:`MSN-004`
2. :req:`LM-CWS-001`
3. :req:`LM-EPS-002`

.. rvt::

   (Precondition "LM on the surface, the crew's part left to the script"
     (lm-ready-for? :standard :surface :manual)
     :heal "Boot a standard mission on the surface with a manual crew"
     (boot-for :standard :surface :manual))

Steps
-----

.. rvt:: A battery fails

   (Verify cwea.master-alarm = false)
   (SetValue bench.battery.2.fault true)
   (RunFor 1)
   (Verify cwea.light.battery = true)
   (Verify cwea.master-alarm = true)

.. rvt:: The crew pushes the master alarm

   (PushMasterAlarm)
   (Verify cwea.master-alarm = false)
   (RunFor 60)
   (Verify cwea.light.battery = true)

.. rvt:: The fault clears

   (SetValue bench.battery.2.fault false)
   (RunFor 1)
   (Verify cwea.light.battery = false)
   (Verify cwea.master-alarm = false)
