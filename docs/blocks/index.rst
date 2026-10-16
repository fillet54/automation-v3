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

Concrete blocks, UUTs and environments live in **plugins**. The framework
provides abstract block contracts and the interpreter; core provides the
generic test blocks and ref helpers. Every plugin loads automatically before
discovery or execution. Subclassing registers blocks, UUTs and environments;
Lisp functions use the registration hook below.

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

Installed plugin packages outside this tree can advertise an entry point.
It names a module with ``register(registry)``, or that function itself:

.. code-block:: toml

   [project.entry-points."automationv3.plugins"]
   my-system = "my_system_plugin"

All bundled and installed plugins load, with core first. No enable list is
needed. Import or registration failures stop loading instead of silently
leaving part of the language unavailable.

Registering Lisp functions
--------------------------------

A plugin package's ``__init__.py`` can expose a registration hook:

.. code-block:: python

   from .refs import Connector

   def register(registry):
       registry.function("my-system/connector", Connector)

The function receives evaluated arguments and can return any script value.
Names such as ``my-system/connector`` avoid collisions. Registration rejects
duplicate names and conflicts with builtins, special forms or blocks.
Registered names and inspectable Python signatures are available to static
analysis. ``registered_functions()`` exposes their plugin and docstrings
for documentation and tooling.

Scripts can shadow a registered default in their own ``core.rst`` or script
scope; that does not change another run's defaults. Register constructors,
calculations and predicates this way. Use blocks for actions and assertions
that need execution results, output and attachments.

Abstract ``Read``, ``SetValue``, ``SetFixedValue`` and ``ClearFixedValue``
contracts live in ``automationv3.framework.value_blocks``. Existing imports
from ``automationv3.plugins.core.value_blocks`` remain compatibility aliases.

Plugins may import from ``automationv3.framework`` only, never from
``services`` or ``web``; ``test/test_layers.py`` checks this.

.. mermaid::
   :caption: The packages, each importing only from those below it (test/test_layers.py)

   flowchart TB
     cli["<b>cli</b><br/>entry points"]
     web["<b>web</b><br/>Flask pages and the job API"]
     services["<b>services</b><br/>storage, the queue, workers, reports"]
     plugins["<b>plugins</b><br/>BuildingBlocks, UUTs, environments"]:::accent
     framework["<b>framework</b><br/>the language, execution, block and UUT contracts"]
     cli --> web
     cli --> services
     web --> services
     web --> framework
     services --> framework
     plugins --> framework

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
