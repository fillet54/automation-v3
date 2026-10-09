================================
Enabling Monitors and Recoveries
================================
Disables a monitor, then only its recovery, and checks each takes
effect.

Requirements
------------
1. :req:`VM-FDIR-003`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Each setting
   :table:

   ("monitor recovery violation action"
     ["both enabled"      [true true true true]
      "monitor disabled"  [false true false false]
      "recovery disabled" [true false true false]])

   (TBD "Set the battery temperature monitor and its recovery as the row says")
   (TBD "Drive +31 degC for 10 s; verify the violation and the action happen as the row says")
