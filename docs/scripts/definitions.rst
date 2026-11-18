Definitions and shared code
===========================

.. rst-class:: lead

   Name values and functions once, and share them through the folder tree.

The two definitions
-------------------

``(def name value)``
   Names a value.

   .. code-block:: clojure

      (def touchdown-vz-limit 3.05)

``(defn name [params] body...)``
   Names a function. Called as a step, it passes unless a block it calls
   fails; to check what it returns, assert it: ``(Verify
   (landed-within-limits?))``.

   .. code-block:: clojure

      (defn landed-within-limits? []
        (and (Read landed)
             (<= (abs (Read touchdown.vz)) touchdown-vz-limit)
             (<= (abs (Read touchdown.vx)) touchdown-vx-limit)))

   A function that calls blocks can group them in the report with ``step``:

   .. code-block:: clojure

      (defn land-and-keep [label]
        (step "Fly to touchdown and attach the trajectory"
          (FlyTo :touchdown)
          (AttachTrajectory label)))

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

      (def program-change-allowed? ...)

A definitions block can be limited to some variations, to override a value for
those variations only; see :ref:`scoped-definitions`.

.. _core-chain:

The ``core.rst`` chain
----------------------

Every folder, including the workspace root, may hold a ``core.rst`` of shared
definitions and declarations. A script loads the ``core.rst`` of every folder
from the root down to its own:

.. mermaid::
   :caption: Each script loads the chain from the root to its folder; an import only adds names

   flowchart TB
     root["core.rst<br/>(uut :lm) (environments :sim :lms)<br/>(def site-radius-m 200)"]
     gdn["GDN/core.rst<br/>(def site-radius-m 100)<br/>(defn climbing? …)"]
     guidance["GDN/tc_gdn_005.rst<br/>site-radius-m is 100"]:::accent
     abort["ABT/tc_abt_001.rst<br/>(import GDN)<br/>site-radius-m is 200, and climbing?"]:::accent
     root -- shadowed by --> gdn
     gdn -- loaded by --> guidance
     root -- loaded by --> abort
     gdn -. "import: adds climbing?,<br/>keeps site-radius-m" .-> abort

Inner definitions shadow outer ones: if ``GDN/`` defined a tighter
``site-radius-m``, every guidance script would use it. (In the Apollo
example it doesn't; the figure shows what would happen.) A ``core.rst`` is a
document too: explain what each definition is for, and the workspace renders
it like any other page.

A ``core.rst`` may only contain documentation, ``def``, ``defn``, ``uut``
and ``environments``.

Imports
-------

``(import FOLDER)`` loads another folder's ``core.rst`` definitions:

.. code-block:: clojure

   (import GDN)

Imports only add definitions. They never override a name the script's own
``core.rst`` chain defines, so importing ``GDN`` into an abort script gets
``climbing?`` without changing anything the abort folder's chain defines. Imports
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
(a function using ``mission`` works only in scripts whose variations bind
it).

A script's own definition of a name shadows any block of the same name, so a
script can stand in for a block while it is being developed.
