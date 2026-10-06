Composing blocks
================

.. rst-class:: lead

   Blocks can be called anywhere in a step: at the top level, inside a
   ``defn``, a ``let`` or an ``if``. Where the call happens decides how it is
   reported and whether a failure stops the step.

At the top level, or in a plain ``defn``
----------------------------------------

A block call acts as its own step: it is reported with its own result, and a
failure stops the statement (and so the script) right there.

.. code-block:: clojure

   (defn start-and-check [pressure]
     (StartDemo {:mode :normal :readings {:brake-pressure pressure}})
     (Verify (reading :brake-pressure) <= max-pressure))

   (start-and-check 60)

If ``StartDemo`` fails, ``Verify`` never runs.

Inside a ``defblock``
---------------------

A ``defblock`` reports as **one** step with its block calls nested beneath it.
Nested failures don't stop it: the ``defblock`` runs to the end and passes on
the truthiness of what it returns (or the block result it returns).

.. code-block:: clojure

   (defblock brakes-hold [pressure]
     (StartDemo {:mode :normal
                 :readings {:brake-pressure pressure}})
     (Verify (reading :brake-pressure) <= max-pressure))

Here the last ``Verify`` decides the result. Use ``defblock`` for a
procedure that should read as one step in a report.

``(passes? expr)``
------------------

Evaluates ``expr`` without letting block failures stop the step, and returns
``true`` or ``false``. Use it to branch on whether something works:

.. code-block:: clojure

   (if (passes? (Verify (reading :brake-pressure) <= 50))
     (set-reading :brake-pressure 70)
     (clear-faults))

The checked call is still reported, marked as checked.

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
   * - top level, ``defn``
     - as its own step
     - stops the step
   * - ``defblock``
     - nested under the defblock
     - doesn't stop it
   * - ``passes?``
     - marked as checked
     - returns ``false``
   * - ``quietly``
     - not shown
     - behaves as where it is called
