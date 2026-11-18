================================================
A Standard LM Can't Stay For An Extended Mission
================================================
Keeps a standard lunar module on the surface towards an extended stay,
and checks the ECS caution warns the crew, before the 75 hours are up,
that its oxygen is running out.

Requirements
------------
1. :req:`LM-ECS-002`

.. rvt::

   (environments :sim)

   (Precondition "A standard LM on the surface"
     (lm-ready? :standard :surface)
     :heal "Boot a standard mission on the surface"
     (boot :standard :surface))

Steps
-----

.. rvt::

   (Wait cwea.light.ecs :within 75h :every 10min)
   (Verify ecs.o2-kg < (* 0.1 22))
   (Verify (Read flight-time) < (* 75 3600))
