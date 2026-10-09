===============
Stale Time Tags
===============
Sends time-tagged NO-OPs tagged in the past and checks those more than
10 s old are rejected and the others executed at once.

Requirements
------------
1. :req:`VM-TC-006`

.. rvt::

   (Precondition "Platform in STANDBY"
     (platform-in-mode? :standby)
     :heal "Command the platform to STANDBY"
     (command-mode :standby))

Steps
-----

.. rvt:: Each age
   :table:

   ("seconds-ago expected-result"
     ["11 s ago" [11 :rejected-stale]
      "10 s ago" [10 :executed]
      "9 s ago"  [9 :executed]])

   (Verify (if (> seconds-ago stale-time-tag-s) :rejected-stale :executed) = expected-result)
   (Verify (SendTC :noop :at (- (now) seconds-ago)) = expected-result)
