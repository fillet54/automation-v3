Lunar module test definitions
=============================
Tests of the Apollo lunar module and its guidance computer's software
(Luminary), against the ``MSN``, ``LM`` and ``LGC`` specifications. They
run against the simulated lunar module, the ``lm`` UUT, reached through
the ``lm`` handle: its points and switches as connectors, declared
below, and the crew station (the DSKY's keys, PRO, the rate-of-descent
switch) through blocks.

Two things decide how a flight starts, and both are chosen at boot with
``StartLM``: the **mission** (``:standard`` or ``:extended``: the
erasable load, and the vehicle it flies) and the **start point**
(``:pdi``, ``:high-gate``, ``:low-gate`` or ``:surface``). The version
under test is the software, the Luminary rope; the mission is not, so
scripts that need both missions have a variation for each.

The rule throughout: cases that can run one after the other on the same
flight are rows of a table block; a case that needs its own boot (another
mission, another start point, an abort that ends the flight) is a
variation.

.. rvt::

   (uut :lm)
   (environments :sim :lms)

Connectors
----------
The lunar module's points, by subsystem. ``panel`` holds the crew's
switches, and ``bench`` the simulator's fault injection. The flight runs
in 0.1 s steps; Wait looks once a second unless a script asks otherwise.

.. rvt::

   (def lgc (connector "lm.lgc"))
   (def dsky (connector "lm.dsky"))
   (def nav (connector "lm.nav"))
   (def truth (connector "lm.truth"))
   (def lr (connector "lm.lr"))
   (def deca (connector "lm.deca"))
   (def engine (connector "lm.engine"))
   (def prop (connector "lm.prop"))
   (def cwea (connector "lm.cwea"))
   (def eps (connector "lm.eps"))
   (def ecs (connector "lm.ecs"))
   (def panel (connector "lm.panel"))
   (def bench (connector "lm.bench"))
   (def touchdown (connector "lm.touchdown"))
   (def contact-light (connector "lm.contact"))
   (def landed (connector "lm.landed"))
   (def staged (connector "lm.staged"))
   (def flight-time (connector "lm.time.sim"))

   (def wait-every 1s)

Numbers from the requirements
-----------------------------

.. rvt::

   (def ft 0.3048)
   (def touchdown-vz-limit 3.05)
   (def touchdown-vx-limit 1.22)
   (def site-radius-m 200)
   (def throttle-min 10)
   (def throttle-max 60)
   (def full-throttle 92.5)
   (def prplnt-low-percent 6)
   (def lamp-test-s 5)
   (def loaded-propellant {:standard 8200 :extended 9000})
   (def planned-stay-h {:standard 33 :extended 75})

What the requirements say, as functions
---------------------------------------

.. rvt::

   (defn within? [value low high]
     (and (>= value low) (<= value high)))

   (defn throttle-allowed? [percent]
     (or (= percent 0)
         (within? percent throttle-min throttle-max)
         (= percent full-throttle)))

   (defn landed-within-limits? []
     (and (Read landed)
          (<= (abs (Read touchdown.vz)) touchdown-vz-limit)
          (<= (abs (Read touchdown.vx)) touchdown-vx-limit)))

Booting the lunar module
------------------------
A precondition checks the LM is booted the way the script needs and
hasn't moved since; its heal boots it. Runs of the same variation can
then reuse a booted LM.

.. rvt::

   (defn lm-ready? [mission start]
     (.ready lm mission start))

   (defn lm-ready-for? [mission start crew]
     (.ready lm mission start crew))

   (defn boot [mission start]
     (StartLM {:mission mission :start start}))

   (defn boot-for [mission start crew]
     (StartLM {:mission mission :start start :crew crew}))
