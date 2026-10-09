=========
Fault Log
=========
Fills the fault log past its size and checks it keeps the last 256
entries across a power cycle.

Requirements
------------
1. :req:`VM-FDIR-007`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Fill and keep

   (TBD "Trigger 300 detections with a test monitor")
   (TBD "Power cycle, dump the fault log, and verify it holds the last 256 in order")
