Brake definitions
=================
Brakes use a tighter pressure limit than the default.

.. rvt::

   (def max-pressure 80)

   (defn brake-pressure-ok? [pressure]
     (within-limit? pressure))

A step form reports its block calls nested beneath one titled entry.
Any call in it that fails stops it, and the script, right there.

.. rvt::

   (defn brakes-hold [pressure]
     (step "Brakes hold the pressure"
       (StartDemo {:mode :normal
                   :readings {:brake-pressure pressure}})
       (Verify (reading :brake-pressure) <= max-pressure)))
