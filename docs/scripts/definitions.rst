Definitions and shared code
===========================

.. rst-class:: lead

   Name values, functions and composite blocks once, and share them through
   the folder tree.

The three definitions
---------------------

``(def name value)``
   Names a value.

   .. code-block:: clojure

      (def max-pressure 100)

``(defn name [params] body...)``
   Names a function. Called as a step, it passes if it returns something
   truthy.

   .. code-block:: clojure

      (defn demo-in-mode? [m]
        (and (.running demo) (= (.mode demo) m)))

``(defblock name [params] body...)``
   Names a composite block. Called as a step, it reports as one step with the
   blocks it calls nested beneath it, and passes on what it returns. See
   :doc:`composing`.

   .. code-block:: clojure

      (defblock brakes-hold [pressure]
        (StartDemo {:mode :normal
                    :readings {:brake-pressure pressure}})
        (Verify (reading :brake-pressure) <= max-pressure))

Definitions are never reported as steps.

A script's definitions section
------------------------------

Definitions that belong to one script go in ``rvt`` blocks marked
``:definitions:``, before any step. The web app shows them collapsed, so the
page leads with the test itself:

.. code-block:: rst

   .. rvt::
      :definitions:

      (def stop-pressure 70)

A definitions block can be limited to some variations, to override a value for
those variations only; see :ref:`scoped-definitions`.

.. _core-chain:

The ``core.rst`` chain
----------------------

Every folder, including the workspace root, may hold a ``core.rst`` of shared
definitions and declarations. A script loads the ``core.rst`` of every folder
from the root down to its own:

.. code-block:: text

   core.rst              (environments :sim) (uut :demo) (def max-pressure 100)
   BRA/core.rst          (def max-pressure 80) (defblock brakes-hold ...)
   BRA/tc_bra_00001.rst  sees max-pressure = 80

Inner definitions shadow outer ones, so ``BRA/`` tightens the limit for every
brake script. A ``core.rst`` is a document too: explain what each definition
is for, and the workspace renders it like any other page.

A ``core.rst`` may only contain documentation, ``def``, ``defn``,
``defblock``, ``uut`` and ``environments``.

Imports
-------

``(import FOLDER)`` loads another folder's ``core.rst`` definitions:

.. code-block:: clojure

   (import BRA)

Imports only add definitions. They never override a name the script's own
``core.rst`` chain defines, so importing ``BRA`` into a fuel script gets
``brakes-hold`` without changing the fuel folder's ``max-pressure``. Imports
must be at the top level of an ``rvt`` block.

Scripts and definitions together
--------------------------------

The ``core.rst`` chain, imports and the script's definitions section load
before any step runs. A definition placed later in a script, between steps,
takes effect where it is, like a step: steps above it can't use it, and if it
fails to evaluate the script fails there.

A script's own definition of a name shadows any block of the same name, so a
script can stand in for a block while it is being developed.
