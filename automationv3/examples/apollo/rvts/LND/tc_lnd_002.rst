==================
Dispersed Landings
==================
Lands from high gate five times, each with its own sensor noise (a
seed), and checks every landing is safe. Queue a few with a filter on
``index``, e.g. ``(< index 2)``.

Requirements
------------
1. :req:`MSN-001`

.. rvt::

   (variations "seed"
     ["seed 1" [1]
      "seed 2" [2]
      "seed 3" [3]
      "seed 4" [4]
      "seed 5" [5]])

   (Precondition "LM at high gate, with the variation's seed"
     (and (lm-ready? :standard :high-gate)
          (= (.get (.config lm) :seed) seed))
     :heal "Boot at high gate with the variation's seed"
     (StartLM {:mission :standard :start :high-gate :seed seed}))

Steps
-----

.. rvt::

   (FlyTo :touchdown)
   (Verify (landed-within-limits?))
   (Verify (abs (Read touchdown.miss-m)) <= site-radius-m)
