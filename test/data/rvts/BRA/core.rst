Brake definitions
=================
Brakes use a tighter pressure limit than the default.

.. rvt::

   (def max-pressure 80)

   (defn brake-pressure-ok? [pressure]
     (within-limit? pressure))

A defblock reports as one step, with the blocks it calls nested beneath
it; it passes on what it returns (here, the last Verify).

.. rvt::

   (defblock brakes-hold [pressure]
     (StartDemo {:mode :normal
                 :readings {:brake-pressure pressure}})
     (Verify (reading :brake-pressure) <= max-pressure))
