Landing definitions
===================
The landings fly the whole way down and keep the flight as attachments.

.. rvt::
   :definitions:

   (defn land-and-keep [label]
     (step "Fly to touchdown and attach the trajectory"
       (FlyTo :touchdown)
       (AttachTrajectory label)))
