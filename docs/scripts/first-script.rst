Your first script
=================

.. rst-class:: lead

   A script is an rst document with code in it. Everything outside the
   ``rvt`` blocks is documentation.

.. code-block:: rst

   ================
   Brake Monitoring
   ================
   Checks the brake pressure stays under the limit.

   Requirements
   ------------
   1. :req:`VMCBRA00001`

   .. rvt::
      :definitions:

      (def target 60)

   Steps
   -----

   .. rvt::

      (set-reading :brake-pressure target)
      (Verify (reading :brake-pressure) <= max-pressure)

The parts
---------

The title
   The document title is the script's name on every page.

``:req:`ID```
   Each ``:req:`` role links the script to a requirement. Reports roll the
   script's results up to these requirements, and the Requirements page lists
   the script under each one. Put them anywhere in the prose; a numbered
   "Requirements" section is the convention.

``.. rvt::``
   A block of script code. Each top-level form in it is one statement:
   a step, a definition, or a directive. Blocks run in document order, so a
   script reads top to bottom as it executes.

``:definitions:``
   Marks a block that only defines things. The web app shows it collapsed,
   and it may only appear before the first step. See :doc:`definitions`.

Steps
   ``(set-reading :brake-pressure target)`` calls a function defined in a
   ``core.rst``; ``(Verify ...)`` calls the ``Verify`` BuildingBlock. Each
   is reported as a step with its own pass/fail badge and duration. See
   :doc:`steps`.

Where things come from
----------------------

``set-reading``, ``reading`` and ``max-pressure`` aren't defined in this
script. They come from the ``core.rst`` files in the script's folder and every
folder above it (see :ref:`core-chain`). ``Verify`` is a BuildingBlock in the
``core`` plugin. ``demo``, the handle used inside ``reading``, is bound to the
UUT the script tests, declared in the root ``core.rst``:

.. code-block:: clojure

   (environments :sim)
   (uut :demo)

A script can override those declarations with its own ``(environments ...)``
or ``(uut ...)``.

What is a script, and what isn't
--------------------------------

Any ``.rst`` file with at least one ``rvt`` block is a script. Plain documents,
such as a folder's ``README.rst``, are rendered as documentation only. A
``core.rst`` is never a script; it holds shared definitions and declarations.

Checking a script
-----------------

The web app lints a script when it renders and before it queues. Lint errors
appear at the top of the script page and stop it being queued. Common ones:

- a ``Precondition`` after a regular step;
- a ``:definitions:`` block after a step, or one that contains a step;
- a ``:variations:`` option naming a variation the script doesn't declare;
- an ``import`` that isn't at the top level;
- a ``core.rst`` containing anything but definitions and declarations.
