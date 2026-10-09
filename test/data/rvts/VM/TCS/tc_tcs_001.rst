==================
Set Points by Mode
==================
Checks each heater circuit uses the thermal table's set points for the
mode the platform is in.

Requirements
------------
1. :req:`VM-TCS-001`

Steps
-----

.. rvt:: Each mode
   :table:

   ("mode"
     ["SAFE"    [:safe]
      "NOMINAL" [:nominal]])

   (BringToMode mode)
   (TBD "Dump the active set points and verify they are the thermal table's for the mode")
