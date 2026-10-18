Rendering blocks
================

.. rst-class:: lead

   A step using your block appears in the rendered script. By default it shows
   as code; a block can render its arguments more readably.

Why render
----------

A reviewer reads the rendered script, not the source. Compare a configuration
written as code:

.. code-block:: clojure

   (StartDemo {:mode :emergency
               :readings {:brake-pressure 70}})

with the same step as ``StartDemo`` renders it: "**Start the demo UUT**"
followed by a two-column *Configuration* table of mode and readings. Both say
the same thing; one is much easier to check against a requirement.

``as_rst``
----------

Return reStructuredText for the step, given the arguments **as written**
(unevaluated):

.. code-block:: python

   from automationv3.framework import markup

   def as_rst(self, *forms):
       return markup.line(markup.strong("Verify"), markup.code(*forms))

The arguments are unevaluated because the page renders the script, not a run:
``max-pressure`` should read as ``max-pressure``, whatever its value.

A block writes reStructuredText, never HTML, because the same step is shown on
live pages, in an exported report's site and in its PDF. Each output renders
the rst its own way. To make part of a step look different, give it a class
(``markup.container("tbd", ...)``) and style the class.

The default ``as_rst`` shows the step as code (``block.code_block(source)``).

Markup helpers
--------------

:mod:`automationv3.framework.markup` escapes values, so nothing from a script
turns into markup, and writes the constructs blocks use most:

``markup.text(value)``
   A value as plain text: strings as they are, everything else as edn.

``markup.code(*values)``
   Values as inline code, separated by spaces.

``markup.strong(text)``, ``markup.line(*parts)``
   Bold text; parts joined into one line (text is escaped, rst kept as is).

``markup.mapping(data, caption=None)``
   A two-column table of a map's keys and values; nested maps become nested
   tables.

``markup.table(headers, rows, caption=None)``
   A table with a header row.

``markup.container(classes, body)``
   ``body`` in a container with classes, for outputs to style.

.. code-block:: python

   def as_rst(self, config):
       return (markup.strong("Start the demo UUT") + "\n\n"
               + markup.mapping(config, caption="Configuration"))

Results
-------

``as_result_rst(result, *forms)`` writes what came of a step in a run's
document, after the step itself. Return ``None`` (the default) for the
standard result: the outcome, duration, message, output, calls and attached
files. ``result.data`` is whatever the block put in its
``BlockResult(..., data=...)``, so a block can show a measurement as a table
or a captured trace as a figure:

.. code-block:: python

   def execute(self, signal):
       samples = capture(signal)
       return BlockResult(ok(samples), data={"signal": signal, "max": max(samples)})

   def as_result_rst(self, result, *forms):
       found = result.data or {}
       return markup.mapping({"Signal": found.get("signal"), "Max": found.get("max")},
                             caption="Captured")

Guidelines
----------

- Lead with what the step does, in words, in bold: "**Start the demo UUT**".
- Show identifiers and values as code (``markup.code``).
- Escape everything that comes from the script (use ``markup.text``).
- Prefer tables for structured arguments; keep a short call on one line.
- Rendering must not fail: a block that can't render a call should return
  ``code_block(...)`` of it.
