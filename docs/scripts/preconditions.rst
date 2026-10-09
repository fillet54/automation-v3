Preconditions
=============

.. rst-class:: lead

   Say what must hold before the steps run, and how to get there. Workers use
   this to run scripts on hardware that is already in the right state.

Writing a precondition
----------------------

.. code-block:: clojure

   (Precondition "Demo running in normal mode"
     (demo-in-mode? :normal)
     :heal "Start the demo in normal mode"
     (start-demo :normal))

The parts, in order:

1. **The description**: what must hold, in words. This is what the script
   page shows.
2. **The check**: a step form whose value is truthy if the state holds.
   Unlike a step, a check is judged by its value: it holds if nothing in it
   failed and its value is truthy.
3. ``:heal``, optionally followed by **a description of the heal**.
4. **The heal**: a step form that establishes the state.

The heal is optional; without it, a failing check can't be fixed:

.. code-block:: clojure

   (Precondition "Demo version at least 1.1.0"
     (demo-version-at-least? "1.1.0"))

Preconditions go before the first regular step (after definitions and
directives). A script may have several; they are checked in order.

How preconditions run
---------------------

A worker runs each precondition's check. If it fails and there is a heal, the
worker runs the heal and checks again. If the check still fails, the run is
:status:`blocked`: the environment couldn't be put into the state the script
needs, which is different from the test failing.

Workers schedule **warm-first**:

1. Every pending job the worker can run is **probed** against the
   environment as it is: its preconditions are checked and healed, without
   reinstalling anything.
2. The first job whose preconditions hold, or heal, runs.
3. Only if none does, the oldest job runs in **force mode**: its UUT versions
   are installed and the UUTs started fresh, then its preconditions run.

So a precondition that states exactly what the script needs, with a cheap
heal, lets jobs that need the same state run back to back on a warm bench.
A script with no preconditions always runs in force mode.

How they are reported
---------------------

On the script page a precondition shows its description, with a subtle mark
when it has a heal. Expanded, it shows the check and, after "If not, heal
by", the heal's description and form.

On a run page a precondition is reported like a titled block: collapsed to its
description and badge, and expanded to show each phase (check, heal, check
again) with the blocks it called.

Preconditions and variations
----------------------------

A precondition can use variation symbols, so each variation states its own
needs:

.. code-block:: clojure

   (Precondition "Demo running in the variation's mode"
     (in-variation-mode?)
     :heal "Start the demo in the variation's mode and pressure"
     (StartDemo {:mode mode
                 :readings {:brake-pressure pressure}}))
