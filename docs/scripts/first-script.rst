Your first script
=================

.. rst-class:: lead

   A script is an rst document with code in it. Everything outside the
   ``rvt`` blocks is documentation.

.. code-block:: rst

   ========================
   The Engine Lights On PRO
   ========================
   Checks the descent engine lights at full throttle once the crew presses
   PRO at powered descent initiation.

   Requirements
   ------------
   1. :req:`LGC-GDN-001`

   .. rvt::
      :definitions:

      (def settle-s 1)

   Steps
   -----

   .. rvt::

      (boot-for :standard :pdi :manual)
      (Proceed)
      (RunFor settle-s)
      (Verify deca.throttle = full-throttle)

The parts
---------

The title
   The document title is the script's name on every page.

``:req:`ID```
   Each ``:req:`` role links the script to a requirement. Reports roll the
   script's results up to these requirements, and the Requirements page lists
   the script under each one. Put them anywhere in the prose; a numbered
   "Requirements" section is the convention.

   Aim for one requirement per script, so a failure points at one
   requirement and a requirement's status reads straight off its scripts. A
   requirement can have several scripts (say, one for the cases that need
   their own run); when splitting isn't practical, list them all.

``.. rvt::``
   A block of script code. Each top-level form in it is one statement:
   a step, a definition, or a directive. Blocks run in document order, so a
   script reads top to bottom as it executes.

``:definitions:``
   Marks a block that only defines things. The web app shows it collapsed,
   and it may only appear before the first step. See :doc:`definitions`.

Steps
   ``(boot-for :standard :pdi :manual)`` calls a function defined in a
   ``core.rst``: it boots the lunar module for a standard mission at
   powered descent initiation, with the script as its crew.
   ``(Proceed)`` and ``(RunFor ...)`` are the lunar module plugin's
   BuildingBlocks, and ``(Verify ...)`` is the core one. Each is reported as
   a step with its own pass/fail badge and duration. See :doc:`steps`.

Where things come from
----------------------

``boot-for``, ``deca`` (the descent engine's control, a connector) and
``full-throttle`` aren't defined in this script. They come from the
``core.rst`` files in the script's folder and every folder above it (see
:ref:`core-chain`). ``lm``, the handle the root ``core.rst``'s functions
use, is bound to the UUT the script tests, declared there:

.. code-block:: clojure

   (uut :lm)
   (environments :sim :lms)

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
