===========
Oxygen Leak
===========
A leak in the descent stage's oxygen tank, on the surface: the ECS
caution must warn the crew while there is still time to lift off.

.. note::

   A flow to review: the bench can inject the leak, but the steps after
   it wait for the ascent stage's oxygen in the model.

Requirements
------------
1. :req:`LM-ECS-002`

.. rvt::

   (Precondition "LM on the surface"
     (lm-ready? :standard :surface)
     :heal "Boot a standard mission on the surface"
     (boot :standard :surface))

Steps
-----

.. rvt:: The leak

   (SetValue bench.o2-leak-kg-h 2)
   (Wait cwea.light.ecs :within 12h :every 10min)

.. rvt:: Time to lift off

   (TBD "The ascent stage's own oxygen lasts to rendezvous")
