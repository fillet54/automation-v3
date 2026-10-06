Developing blocks
=================

.. rst-class:: lead

   A guide for Python developers: the BuildingBlocks scripts call, how they
   render in a script, and the UUTs and environments they reach.

Script writers compose; block developers provide the pieces. Anything that
talks to hardware, needs a library, or deserves careful engineering and
testing belongs in Python, behind a block with a clear syntax and a good
rendering.

Plugins
-------

Blocks, UUTs and environments live in **plugins**: Python modules under the
``automationv3.plugins`` package. Every module in it is imported when the
framework loads, and subclassing registers the class; there is no other
registration step.

.. code-block:: text

   automationv3/plugins/
     core/          Verify, Wait: available to every script
       verify.py
       wait.py
     sample/        the demo UUT, the sim and bench environments, StartDemo
       demo.py
       blocks.py

Add your own as a new package beside them, with an ``__init__.py`` that
imports its modules.

Plugins may import from ``automationv3.framework`` only, never from
``services`` or ``web``; ``test/test_layers.py`` checks this.

In this section
---------------

:doc:`writing-blocks`
   A BuildingBlock from the ground up: syntax checks, evaluated and
   unevaluated arguments, results and the running script's context.

:doc:`rendering`
   How a step using your block reads in a rendered script.

:doc:`attachments`
   Attaching files (logs, captures, snapshots) to a run.

:doc:`uuts-and-environments`
   Plugging in new units under test and the environments they run in.

The API itself is in :doc:`../reference/api`.
