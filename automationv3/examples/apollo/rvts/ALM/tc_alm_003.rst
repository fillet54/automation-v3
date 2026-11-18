===================================
Propellant Remaining And PRPLNT LOW
===================================
From low gate, hovers until the computer lights PRPLNT LOW, and checks
both what it shows for the propellant remaining (N93) and when the
caution comes on are shares of the propellant this mission loaded. Then
hovers on until the tanks' own low-level sensor lights DES QTY.

.. note::

   Fails on purpose with LUM131 in the extended mission: it computes the
   propellant remaining against the standard mission's load, so N93 reads
   high and the caution comes on late (a defect invented for this
   example, fixed in LUM210).

Requirements
------------
1. :req:`LGC-PRP-001`
2. :req:`LGC-PRP-002`
3. :req:`LM-PRP-003`

.. rvt::

   (variations "mission"
     ["standard" [:standard]
      "extended" [:extended]])

   (Precondition "LM at low gate for the variation's mission, flown by the script"
     (lm-ready-for? mission :low-gate :manual)
     :heal "Boot the variation's mission at low gate with a manual crew"
     (boot-for mission :low-gate :manual))

Steps
-----

.. rvt:: N93 against the loaded propellant

   (let [loaded (.get loaded-propellant mission)
         actual (* 100 (/ (Read prop.descent-kg) loaded))]
     (Verify (abs (- (Read lgc.prop-percent) actual)) < 0.2))

.. rvt:: Hover

   (ClickROD 1)
   (ClickROD (round (/ (- (Read lgc.rate-command)) ft)))
   (RunFor 10)
   (Verify (abs (Read truth.altitude-rate)) < 0.5)

.. rvt:: PRPLNT LOW at 6% of the load

   (Wait cwea.light.prplnt-low :within 5min)
   (let [loaded (.get loaded-propellant mission)]
     (Verify (Read prop.descent-kg) within? (* 0.059 loaded) (* 0.061 loaded)))

.. rvt:: DES QTY at 5.6% of the tanks

   (Verify cwea.light.des-qty = false)
   (Wait cwea.light.des-qty :within 2min)
   (Verify prop.low-level = true)
   (let [loaded (.get loaded-propellant mission)]
     (Verify (Read prop.descent-kg) within? (* 0.055 loaded) (* 0.057 loaded)))
