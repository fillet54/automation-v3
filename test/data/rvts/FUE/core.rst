Fuel definitions
================

.. rvt::

   (def tank-capacity 50)

   (defn fuel-level-ok? [litres]
     (<= litres tank-capacity))
