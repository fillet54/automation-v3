Composing blocks
================

.. rst-class:: lead

   Blocks can be called anywhere in a step: at the top level, inside a
   ``defn``, a ``let`` or an ``if``. Wherever the call is, it reports and fails
   the same way. Three forms change that, and they say so where they are used.

Wherever it is called
---------------------

A block call is reported with its own result, and a failure stops the
statement (and so the script) right there. A ``defn`` is transparent: the
blocks it calls report as calls of the step that called it.

.. code-block:: clojure

   (defn start-and-check [pressure]
     (StartDemo {:mode :normal :readings {:brake-pressure pressure}})
     (Verify (reading :brake-pressure) <= max-pressure))

   (start-and-check 60)

If ``StartDemo`` fails, ``Verify`` never runs.

``(step "title" body...)``
--------------------------

Groups the block calls of its body under one entry in the report, with the
title, nested beneath it. A failure inside still stops it, and the step
around it. It gives the body's value.

.. code-block:: clojure

   (defn brakes-hold [pressure]
     (step "Brakes hold the pressure"
       (StartDemo {:mode :normal
                   :readings {:brake-pressure pressure}})
       (Verify (reading :brake-pressure) <= max-pressure)))

Use it for a procedure that should read as one step in a report.

``(try-ok? form)``
------------------

Runs the form and gives ``true`` if no block call in it failed, ``false`` if
one did, without stopping the step. Use it to branch on whether something
works:

.. code-block:: clojure

   (if (try-ok? (Verify (reading :brake-pressure) <= 50))
     (set-reading :brake-pressure 70)
     (clear-faults))

The calls inside are still reported, marked as suppressed (shown as true or
false rather than passed or failed).

``(try form default)``
----------------------

Like ``try-ok?``, but gives the form's value, or ``default`` (evaluated) if a
block call in it failed:

.. code-block:: clojure

   (def version (try (InstalledVersion :demo) "unknown"))

``try-ok?`` and ``try`` only catch block failures. A mistake in the script's
own code, such as an unknown name, still stops the step.

Only the last check counts
--------------------------

To run several checks and let only the last decide, suppress the earlier ones
explicitly:

.. code-block:: clojure

   (step "Settles within limits"
     (try-ok? (Verify (reading :brake-pressure) <= 60))   ; may overshoot
     (Wait 2)
     (Verify (reading :brake-pressure) <= 60))

``(quietly forms...)``
----------------------

Runs the forms with their block calls left out of the output. Calls still run
and fail as usual. Use it for housekeeping that would clutter the report.

.. code-block:: clojure

   (quietly
     (StartDemo {:mode :normal}))

Summary
-------

.. list-table::
   :header-rows: 1
   :widths: 30 35 35

   * - Called in
     - Reported
     - A failure
   * - top level, ``defn``, ``let``, ``if``...
     - as a call of the step
     - stops the step
   * - ``step``
     - nested under its title
     - stops it, and the step
   * - ``try-ok?``, ``try``
     - marked as suppressed
     - gives ``false``, or the default
   * - ``quietly``
     - not shown
     - behaves as where it is called
