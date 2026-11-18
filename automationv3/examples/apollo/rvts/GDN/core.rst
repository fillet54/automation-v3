Guidance definitions
====================
What the guidance tests share: the approach angle each mission's
erasable load gives, where low gate is, and how to tell the LM is
climbing.

.. rvt::

   (def low-gate {:downrange -320 :altitude 150})

   (defn degrees [radians]
     (* radians (/ 180 pi)))

   (defn approach-angle-from [downrange altitude]
     (degrees (atan (/ (- altitude (.get low-gate :altitude))
                       (- (.get low-gate :downrange) downrange)))))

   (defn climbing? []
     (> (Read truth.altitude-rate) 0))
