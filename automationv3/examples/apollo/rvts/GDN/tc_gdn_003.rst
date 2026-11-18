================================
High Gate And The Approach Angle
================================
Flies to high gate and checks P64 takes over there, on the approach angle
the variation's erasable load gives: the extended missions' landing
sites, in mountains, called for a steeper approach.

Requirements
------------
1. :req:`LGC-GDN-003`

.. rvt::
   :definitions:
   :variations: standard

   (def approach-deg 16)

.. rvt::
   :definitions:
   :variations: extended

   (def approach-deg 25)

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

.. rvt:: P63 hands over to P64 at high gate

   (FlyTo :high-gate)
   (Verify lgc.program = 64)

.. rvt:: On the load's approach angle

   (Verify (approach-angle-from (Read truth.downrange) (Read truth.altitude))
           within? (- approach-deg 2.5) (+ approach-deg 2.5))

.. rvt-variant::
   :variations: extended

   The extended approach comes in steeper, so from high gate the landing
   site is closer as well as lower.

   .. rvt:: Closer at high gate

      (Verify truth.downrange > -6000)
