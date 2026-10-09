====================================
Telecommands From Either Transponder
====================================
Sends a NO-OP through each transponder and checks each is accepted and
executed.

Requirements
------------
1. :req:`VM-TC-001`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Each transponder
   :table:

   ("via"
     ["transponder A" [:a]
      "transponder B" [:b]])

   (let [before (Telemetry :noop-count)]
     (Verify (SendTC :noop :via via) = :executed)
     (Verify (Telemetry :noop-count) = (+ before 1)))
