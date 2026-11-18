===============
Rate Of Descent
===============
From low gate, flies the landing by hand in P66: the first click of the
rate-of-descent switch selects P66, each one after it changes the
commanded rate by 1 ft/s, and P66 holds that rate with the throttle.

Requirements
------------
1. :req:`LGC-GDN-004`

.. rvt::

   (Precondition "LM at low gate, flown by the script"
     (lm-ready-for? :standard :low-gate :manual)
     :heal "Boot a standard mission at low gate with a manual crew"
     (boot-for :standard :low-gate :manual))

Steps
-----

.. rvt:: The first click selects P66

   (ClickROD 1)
   (Verify lgc.program = 66)

Each row clicks, checks the commanded rate moved by that many feet a
second, and that the LM settles on it. In order, they slow the descent
from low gate's 8 m/s or so to about 1 m/s.

.. rvt:: Each click changes the rate by 1 ft/s
   :table:

   ("clicks"
     ["five up"        [5]
      "five up again"  [5]
      "five up, again" [5]
      "five up, last"  [5]
      "one down"       [-1]
      "three up"       [3]
      "two up"         [2]])

   (let [before (Read lgc.rate-command)]
     (ClickROD clicks)
     (Verify (abs (- (Read lgc.rate-command) (+ before (* clicks ft)))) < 0.001))
   (RunFor 5)
   (Verify nav.altitude-rate within? (- (Read lgc.rate-command) 0.3)
                                     (+ (Read lgc.rate-command) 0.3))

.. rvt:: Down to contact

   (Wait contact-light :within 5min)
   (FlyTo :touchdown)
   (Verify (landed-within-limits?))
