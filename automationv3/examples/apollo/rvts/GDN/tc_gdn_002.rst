==================
Throttle Positions
==================
Flies the whole descent and checks the descent engine only ever ran at
full throttle or within its throttling range, and throttled down for
good once it left full throttle.

Requirements
------------
1. :req:`LM-PRP-001`
2. :req:`LGC-GDN-002`

.. rvt::

   (variations "mission"
     ["standard" [:standard]
      "extended" [:extended]])

   (Precondition "LM booted for the variation's mission, at PDI"
     (lm-ready? mission :pdi)
     :heal "Boot the variation's mission at PDI"
     (boot mission :pdi))

Steps
-----

.. rvt:: Braking at full throttle

   (FlyTo :ignition)
   (RunFor 2)
   (Verify deca.throttle = full-throttle)

.. rvt:: Throttle down

   (FlyTo :throttle-down)
   (RunFor 2)
   (Verify deca.throttle within? throttle-min throttle-max)

.. rvt:: The rest of the descent

   (FlyTo :touchdown)
   (let [bad (filter (fn [t] (not (throttle-allowed? t))) (.throttles lm))
         full-again (filter (fn [t] (= t full-throttle)) (.throttles lm :throttle-down))]
     (Verify (count bad) = 0)
     (Verify (count full-again) = 0))
