==================
Momentum Unloading
==================
Builds up reaction wheel momentum and checks the magnetorquers unload it
once any wheel passes 80% of its capacity.

Requirements
------------
1. :req:`VM-AOCS-006`

.. rvt::

   (Precondition "Platform in NOMINAL"
     (platform-in-mode? :nominal)
     :heal "Command the platform to NOMINAL"
     (command-mode :nominal))

Steps
-----

.. rvt:: Build up momentum

   (TBD "Apply a constant simulated disturbance torque about the pitch axis")
   (TBD "Verify the magnetorquers stay off while every wheel is below wheel-unload-fraction (80%)")

.. rvt:: Unload

   (TBD "Verify unloading starts within one control cycle of the pitch wheel passing 80%")
   (TBD "Verify the wheel momentum falls back below 80% and the attitude error stays under 1 deg")
