===========================
Landing Point Redesignation
===========================
The commander moves the landing site past a boulder field in P64, with
the attitude controller, and the approach retargets to the new site.

.. note::

   A flow to review: the model doesn't fly redesignation yet, so its
   steps are ``(TBD)`` and the run comes out incomplete.

Requirements
------------
1. :req:`MSN-003`

.. rvt::

   (Precondition "LM at high gate"
     (lm-ready? :standard :high-gate)
     :heal "Boot a standard mission at high gate"
     (boot :standard :high-gate))

Steps
-----

.. rvt:: Read the look angle on N64

   (TBD "V06 N64: the landing site's look angle on the window grid")

.. rvt:: Redesignate past the boulders

   (TBD "Two clicks long on the attitude controller; the site moves about 400 m downrange")

.. rvt:: Land at the new site

   (FlyTo :touchdown)
   (TBD "Touchdown within 200 m of the new site, not the original one")
