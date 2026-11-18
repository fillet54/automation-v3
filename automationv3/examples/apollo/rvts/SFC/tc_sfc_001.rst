========================
The Planned Surface Stay
========================
Stays on the surface for the variation's planned stay and checks no
caution or warning came on, with oxygen, water and power to spare.
Simulated only: the extended stay is three days.

Requirements
------------
1. :req:`MSN-010`

.. rvt::

   (environments :sim)

   (variations "mission"
     ["standard" [:standard]
      "extended" [:extended]])

   (Precondition "LM on the surface for the variation's mission"
     (lm-ready? mission :surface)
     :heal "Boot the variation's mission on the surface"
     (boot mission :surface))

Steps
-----

.. rvt::

   (RunFor (* 3600 (.get planned-stay-h mission)))
   (Verify cwea.caution = false)
   (Verify cwea.warning = false)
   (Verify ecs.o2-kg > 0)
   (Verify ecs.water-kg > 0)
   (Verify eps.ah > 0)
