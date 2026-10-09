======================
Hazardous Telecommands
======================
Sends each hazardous telecommand, armed and not, and checks it executes
only when armed within the previous 30 s, by the pulse on its actuator
drive line.

Requirements
------------
1. :req:`VM-TC-007`

.. rvt::

   (Precondition "Platform in MANEUVER, so propulsion is enabled"
     (platform-in-mode? :maneuver)
     :heal "Command the platform to MANEUVER"
     (command-mode :maneuver))

Steps
-----

.. rvt:: Each command
   :table:

   ("command arm-delay-s expected-result"
     ["valve, unarmed"      [:propulsion-valve-open nil :rejected-not-armed]
      "valve, armed 5 s"    [:propulsion-valve-open 5   :executed]
      "valve, armed 31 s"   [:propulsion-valve-open 31  :rejected-not-armed]
      "deploy, armed 29 s"  [:deployment-fire 29        :executed]
      "image, unarmed"      [:image-overwrite nil       :rejected-not-armed]
      "image, armed 30 s"   [:image-overwrite 30        :executed]])

   (Verify (if (nil? arm-delay-s)
             :rejected-not-armed
             (if (<= arm-delay-s arm-window-s) :executed :rejected-not-armed))
           = expected-result)
   (let [pulses (.pulse_count vm command)]
     (if (some? arm-delay-s)
       (do (Verify (SendTC :arm :command command) = :executed)
           (RunFor arm-delay-s)))
     (Verify (SendTC command) = expected-result)
     (Verify (- (.pulse_count vm command) pulses)
             = (if (= expected-result :executed) 1 0)))
