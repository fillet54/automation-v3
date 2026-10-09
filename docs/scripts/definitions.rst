Definitions and shared code
===========================

.. rst-class:: lead

   Name values and functions once, and share them through the folder tree.

The two definitions
-------------------

``(def name value)``
   Names a value.

   .. code-block:: clojure

      (def max-pressure 100)

``(defn name [params] body...)``
   Names a function. Called as a step, it passes unless a block it calls
   fails; to check what it returns, assert it: ``(Verify (demo-in-mode?
   :normal))``.

   .. code-block:: clojure

      (defn demo-in-mode? [m]
        (and (.running demo) (= (.mode demo) m)))

   A function that calls blocks can group them in the report with ``step``:

   .. code-block:: clojure

      (defn brakes-hold [pressure]
        (step "Brakes hold the pressure"
          (StartDemo {:mode :normal
                      :readings {:brake-pressure pressure}})
          (Verify (reading :brake-pressure) <= max-pressure)))

Definitions are never reported as steps, and only appear at the top level of
a ``core.rst`` or a script, never inside another form (a ``defn``, a
``let``...). That is what lets every name a script uses be checked before it
runs; see :ref:`checked-before-running`.

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
   BRA/core.rst          (def max-pressure 80) (defn brakes-hold ...)
   BRA/tc_bra_00001.rst  sees max-pressure = 80

Inner definitions shadow outer ones, so ``BRA/`` tightens the limit for every
brake script. A ``core.rst`` is a document too: explain what each definition
is for, and the workspace renders it like any other page.

A ``core.rst`` may only contain documentation, ``def``, ``defn``, ``uut``
and ``environments``.

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
takes effect where it is, like a step: steps above it can't use it (the static
check says so), and if it fails to evaluate the script ends in error there.

.. _checked-before-running:

Checked before running
----------------------

Because definitions only live at the top level, the names a script can use
are known without running it: builtins, the ``core.rst`` definitions, the
script's own definitions in order, UUT handles and variation symbols (bound
after the definitions section loads), and the parameters and ``let`` names
in scope. A name that is none of these is an error before the script can be
queued, shown by the statement it is in, with a suggestion when one is
close. A ``core.rst`` function's names are checked when a script can call
it, since a ``core.rst`` may serve scripts that bind more than this one
(``in-variation-mode?`` uses ``mode``, which only scripts with variations
bind).

A script's own definition of a name shadows any block of the same name, so a
script can stand in for a block while it is being developed.
