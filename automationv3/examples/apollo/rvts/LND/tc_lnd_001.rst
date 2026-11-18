================================
Landing Within The Gear's Limits
================================
Flies each mission down from powered descent initiation, and from high
gate, with the nominal crew, and checks the touchdown: within the
landing gear's limits, within 200 m of the site, with no caution lit.
The trajectory is attached to each run, as a table and as a plot.

Requirements
------------
1. :req:`MSN-001`
2. :req:`LM-GNC-001`
3. :req:`LM-LDG-001`
4. :req:`LM-LDG-002`

.. rvt::

   (variations "mission start"
     ["standard from PDI"       [:standard :pdi]
      "standard from high gate" [:standard :high-gate]
      "extended from PDI"       [:extended :pdi]
      "extended from high gate" [:extended :high-gate]])

   (Precondition "LM booted for the variation's mission, at its start point"
     (lm-ready? mission start)
     :heal "Boot the variation's mission at its start point"
     (boot mission start))

.. rvt-variant::
   :variations: standard from PDI, standard from high gate

   A standard mission flies a 16° approach to a site on the maria, as
   Apollo 11 to 14 did.

.. rvt-variant::
   :variations: extended from PDI, extended from high gate

   An extended mission is heavier, with more propellant, and flies a 25°
   approach into a site among mountains, as Apollo 15 to 17 did.

Steps
-----

.. rvt:: Down to the surface

   (FlyTo :contact)
   (Verify contact-light = true)
   (land-and-keep "descent")

.. rvt:: The touchdown

   (Verify (abs (Read touchdown.vz)) <= touchdown-vz-limit)
   (Verify (abs (Read touchdown.vx)) <= touchdown-vx-limit)
   (Verify (abs (Read touchdown.miss-m)) <= site-radius-m)
   (Verify cwea.caution = false)
