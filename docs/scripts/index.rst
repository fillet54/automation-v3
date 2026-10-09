Writing scripts
===============

.. rst-class:: lead

   A guide for test authors: how a script is put together, from a single
   Verify to variations, preconditions and shared definitions.

A script is an ``.rst`` file in a workspace. You write it in your editor,
commit it to git, and the web app renders, lints and queues it. Nothing here
needs Python: the steps call BuildingBlocks that block developers provide, and
the definitions you write yourself are in a small Lisp.

While a script is under development, run it from the
:doc:`scratch space <../operating/scratch>` (it uses your working tree,
uncommitted edits included) or from the command line with
``automation-v3 run``.

In this section
---------------

:doc:`first-script`
   The anatomy of a script: title, requirements, ``rvt`` blocks, steps.

:doc:`steps`
   What makes a step, how it passes or fails, and the forms you can write.

:doc:`definitions`
   ``def`` and ``defn``; the ``core.rst`` chain and imports; checks before
   running.

:doc:`variations`
   Running one script several ways, and blocks and prose that only apply to
   some of them.

:doc:`preconditions`
   Stating the state a script needs, and how to heal into it.

:doc:`composing`
   Blocks inside definitions: ``step``, ``try-ok?``, ``try`` and ``quietly``.

:doc:`documenting`
   Making the rendered script read well: titles, variants and prose.

:doc:`blocks`
   Every BuildingBlock you can call, with its usage and documentation.

A complete example
------------------

This is ``BRA/tc_bra_00004.rst`` from the sample set. Every piece of it is
explained in the pages that follow.

.. literalinclude:: ../../test/data/rvts/BRA/tc_bra_00004.rst
   :language: rst
