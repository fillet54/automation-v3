=========================
Executive Overflow (1202)
=========================
Flies the descent with the rendezvous radar's angle counters running
away, as on Apollo 11, once with its mode switch at LGC and once at
AUTO.

Requirements
------------
1. :req:`LGC-ALM-001`
2. :req:`LGC-ALM-002`

.. rvt::

   (variations "rr-mode expect-alarms"
     ["RR at LGC"  [:lgc false]
      "RR at AUTO" [:auto true]])

   (Precondition "LM at PDI"
     (lm-ready? :standard :pdi)
     :heal "Boot a standard mission at PDI"
     (boot :standard :pdi))

.. rvt-variant::
   :variations: RR at AUTO

   On Apollo 11 the rendezvous radar's switch was at AUTO, and a fault in
   its power supply's phase made its angle counters stream pulses into
   the computer, taking about 15% of its time. With the crew's V16 N68
   display on top of the braking phase's work, the computer ran out of
   time and raised 1202: it restarted, dropped the display, and flew on.

Steps
-----

.. rvt:: The counters run away

   (SetValue panel.rr-mode rr-mode)
   (SetValue bench.rr-cdu-fault true)

.. rvt:: The descent

   (FlyTo :touchdown)
   (Verify (landed-within-limits?))

.. rvt:: Alarms only at AUTO, and a restart for each

   (Verify (> (count (Read lgc.alarms)) 0) = expect-alarms)
   (Verify lgc.restarts = (count (Read lgc.alarms)))
   (Verify (= (count (filter (fn [code] (not= code 1202)) (Read lgc.alarms))) 0))

.. rvt-variant::
   :variations: RR at AUTO

   .. rvt:: Each alarm sounded the master alarm

      (Verify (count (.events lm :program-alarm)) = (count (Read lgc.alarms)))
      (Verify (>= (count (filter (fn [e] (= (.get e :light) :prog)) (.events lm :caution))) 1))
