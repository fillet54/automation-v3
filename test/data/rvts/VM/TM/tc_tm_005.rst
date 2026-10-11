=========================
Recording Without Contact
=========================
Checks housekeeping is recorded during and between ground contacts.

Requirements
------------
1. :req:`VM-TM-005`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Run a 10 minute contact, then 10 minutes without one

   (TBD)

.. rvt:: Dump the housekeeping packet store and verify it holds every packet from both periods

   (TBD)
