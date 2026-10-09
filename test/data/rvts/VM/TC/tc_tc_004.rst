=================
Telecommand Order
=================
Sends five numbered NO-OPs in one burst and checks they are executed,
and reported, in the order received.

Requirements
------------
1. :req:`VM-TC-004`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Five NO-OPs

   (step "Five NO-OPs, numbered"
     (SendTC :noop :seq 1)
     (SendTC :noop :seq 2)
     (SendTC :noop :seq 3)
     (SendTC :noop :seq 4)
     (SendTC :noop :seq 5))
   (Verify (.report_seqs vm 5) = [1 2 3 4 5])
