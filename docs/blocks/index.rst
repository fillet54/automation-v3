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

Adding to documents
-------------------

Scripts, runs and reports are reStructuredText documents (see
:doc:`../reference/report-documents`). A block renders its own steps and
results (:doc:`rendering`); the registration hook can add the rest:

.. code-block:: python

   from pathlib import Path
   from docutils.parsers.rst import directives

   def coverage(context, options):
       """.. signal-coverage::  rst for the report's document"""
       if context.data is None:          # a page with no report around it
           return ""
       return context.render("my-system/coverage.rst", runs=context.data.runs)

   def register(registry):
       registry.directive("signal-coverage", coverage, {"subsystem": directives.unchanged})
       registry.snippets(Path(__file__).parent / "snippets")
       registry.css(".ui-document .coverage td { font-family: var(--ui-font-mono); }")
       registry.latex(r"\newenvironment{sphinxclasscoverage}{\small}{}")

``registry.directive(name, resolver, option_spec=None, arguments=False)``
   A directive documents can use. ``resolver(context, options)`` writes it, as
   reStructuredText: ``context.data`` is the report (its runs, combinations,
   requirements and their events, see ``services/reports/data.py``),
   ``context.run`` the run of a run's page, ``context.render(snippet, **values)``
   renders a snippet. Parsing never reads data, so a document parses once and
   resolves on each show or build.

``registry.role(name, value)``
   A role: ``:name:`what``` is ``value(context, what)``, inline
   reStructuredText.

``registry.filter(name, fn)``
   A filter every snippet can use.

``registry.snippets(folder)``
   Snippets by name (``my-system/coverage.rst``), for the plugin's directives,
   or overriding the built-in ones. A workspace's report template overrides
   them in turn.

``registry.css(text)``, ``registry.latex(text)``
   How the classes the plugin's output carries look: on live pages and in a
   frozen report's site (CSS), and in its PDF (LaTeX for its preamble, such as
   ``sphinxclass<class>`` environments and ``\DUrole<class>`` commands).

The same directive serves a live page (docutils, resolved from the data as it
is now), a frozen report's site and its PDF (Sphinx), so write only what plain
docutils knows, with classes for what each output should style its own way.
Names are claimed once: a directive, role, filter or snippet another plugin
or the framework already has is a load error. A frozen report's build records
which plugins, at which versions, built it. ``plugins/sample/documents.py``
is a complete example: ``.. attached-files::`` lists the files a report's runs
attached.

Abstract ``Read``, ``SetValue``, ``SetFixedValue`` and ``ClearFixedValue``
contracts live in ``automationv3.framework.value_blocks``. Existing imports
from ``automationv3.plugins.core.value_blocks`` remain compatibility aliases.

Plugins may import from ``automationv3.framework`` (and
``automationv3.documents``, rendering at the framework's level) only, never
from ``services`` or ``web``; ``test/test_layers.py`` checks this.

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
