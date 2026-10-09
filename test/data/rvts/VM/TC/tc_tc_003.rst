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
     ["valve-unarmed"      [:propulsion-valve-open nil :rejected]
      "valve-armed"        [:propulsion-valve-open 5   :executed]
      "valve-arm-expired"  [:propulsion-valve-open 31  :rejected]
      "deploy-armed"       [:deployment-fire 29        :executed]
      "image-overwrite"    [:image-overwrite nil       :rejected]
      "code-patch-armed"   [:code-memory-patch 10      :executed]])

   (Precondition "Platform in STANDBY on the propulsion test harness"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: The expected result follows the arm window

   (Verify (if (nil? arm-delay-s)
             :rejected
             (if (<= arm-delay-s arm-window-s) :executed :rejected))
           = expected-result)

.. rvt:: Arm and send

   (TBD "If arm-delay-s is given, send the arm telecommand for the command, then wait arm-delay-s")
   (TBD "Send the hazardous telecommand, with its actuator output disconnected from the harness")
   (TBD "Verify the result is expected-result")
   (TBD "Verify the actuator drive line pulsed only if expected-result is executed")

.. rvt:: Hardware-decoded commands

   (TBD "Stop the VM's telecommand task with the test hook")
   (TBD "Send the hardware-decoded safe-mode command and verify the safe-mode discrete is set")
   (TBD "Send the hardware-decoded reset command and verify the bus computer resets")
