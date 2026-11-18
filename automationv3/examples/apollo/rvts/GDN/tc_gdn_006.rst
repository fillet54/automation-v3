=====================
Landing Radar And V57
=====================
Navigation starts the descent with an altitude error. Checks the landing
radar's data is left out until the crew keys V57, that it then corrects
the altitude, that N68 shows the difference, and that a failed radar
lights its caution.

Requirements
------------
1. :req:`LGC-NAV-001`
2. :req:`LGC-NAV-002`
3. :req:`LM-LDG-003`

.. rvt::

   (Precondition "LM at PDI, the crew's part left to the script"
     (lm-ready-for? :standard :pdi :manual)
     :heal "Boot a standard mission at PDI with a manual crew"
     (boot-for :standard :pdi :manual))

Steps
-----

.. rvt:: The radar sees the surface below 12 km

   (Proceed)
   (Verify lr.alt-good = false)
   (Wait lr.alt-good :within 10min)
   (Verify truth.altitude < 12000)

.. rvt:: Before V57, its data is left out

   (let [delta-h (Read nav.delta-h)]
     (Verify (abs delta-h) > 500)
     (RunFor 10)
     (Verify (abs (Read nav.delta-h)) > (* 0.9 (abs delta-h))))

.. rvt:: N68 shows delta-H

   (Keys "V16N68E")
   (Verify (abs (- (Read dsky.r3) (Read nav.delta-h))) < 1)

.. rvt:: After V57, navigation takes it in

   (Keys "V57E")
   (RunFor 20)
   (Verify (abs (Read nav.delta-h)) < 50)

.. rvt:: A failed radar

   (SetValue bench.lr-failed true)
   (RunFor 2)
   (Verify lr.alt-good = false)
   (Verify cwea.light.ldg-rdr = true)
   (SetValue bench.lr-failed false)
   (RunFor 2)
   (Verify cwea.light.ldg-rdr = false)
