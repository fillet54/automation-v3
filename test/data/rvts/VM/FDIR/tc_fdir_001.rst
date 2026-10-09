=================
Limit Persistence
=================
Drives a monitored parameter out of limits for less than, then as long
as, its persistence, and checks when a violation is declared.

Requirements
------------
1. :req:`VM-FDIR-001`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Each duration
   :table:

   ("samples declared"
     ["2 samples" [2 false]
      "3 samples" [3 true]])

   (TBD "Drive the battery temperature to +31 degC (limit +30, persistence 3) for the row's samples")
   (TBD "Verify a limit violation is declared exactly when declared is true")
