============
Setting Time
============
Sets and adjusts on-board time by telecommand, and checks a large
adjustment is refused with a time-tagged command due.

Requirements
------------
1. :req:`VM-TIM-004`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Each adjustment
   :table:

   ("adjust-s command-due expected-result"
     ["small, nothing due" [0.5 false :executed]
      "large, nothing due" [2.0 false :executed]
      "small, command due" [0.5 true :executed]
      "large, command due" [2.0 true :rejected]])

   (TBD "If command-due, load a time-tagged NO-OP due in 30 s")
   (TBD "Command a time adjustment of adjust-s and verify the result is expected-result")
