======================
Hazardous Telecommands
======================
Checks each hazardous telecommand is rejected unless armed within the
previous 30 s, and that the hardware-decoded commands work even with the
VM's own command processing stopped.

Requirements
------------
1. :req:`VM-TC-007`
2. :req:`VM-TC-008`
3. :req:`VM-MEM-006`

.. rvt::

   (variations "command arm-delay-s expected-result"
     ["valve-unarmed"      [:propulsion-valve-open nil :rejected-not-armed]
      "valve-armed"        [:propulsion-valve-open 5   :executed]
      "valve-arm-expired"  [:propulsion-valve-open 31  :rejected-not-armed]
      "deploy-armed"       [:deployment-fire 29        :executed]
      "image-overwrite"    [:image-overwrite nil       :rejected-not-armed]
      "code-patch-armed"   [:code-memory-patch 10      :executed]])

   (Precondition "Platform in MANEUVER, so propulsion is enabled"
     (platform-in-mode? :maneuver)
     :heal "Command the platform to MANEUVER"
     (command-mode :maneuver))

Steps
-----

.. rvt:: The expected result follows the arm window

   (Verify (if (nil? arm-delay-s)
             :rejected-not-armed
             (if (<= arm-delay-s arm-window-s) :executed :rejected-not-armed))
           = expected-result)

.. rvt:: Arm and send

   (def pulses-before (.pulse_count vm command))
   (if (some? arm-delay-s)
     (do (Verify (SendTC :arm :command command) = :executed)
         (RunFor arm-delay-s)))
   (Verify (SendTC command) = expected-result)
   (Verify (- (.pulse_count vm command) pulses-before)
           = (if (= expected-result :executed) 1 0))

.. rvt:: Hardware-decoded commands

   (.stop_tc_task vm)
   (Verify (SendTC :noop) = :lost)
   (.hw_command vm :safe)
   (Verify (Telemetry :safe-discrete))
   (Verify (Telemetry :mode) = :safe)
   (.hw_command vm :reset)
   (Verify (Telemetry :reset-cause) = :commanded)
