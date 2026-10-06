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

``as_html``
-----------

Return HTML for the step, given the arguments **as written** (unevaluated):

.. code-block:: python

   def as_html(self, *forms):
       return (
           "<span><strong>Verify</strong> "
           f'<span class="ui-mono">{" ".join(html.text(f) for f in forms)}</span>'
           "</span>"
       )

Return ``None`` to fall back to the default.

The arguments are unevaluated because the page renders the script, not a run:
``max-pressure`` should read as ``max-pressure``, whatever its value.

``as_rst``
----------

Return reStructuredText instead, when rst expresses it better. The default
``as_rst`` uses ``as_html`` if it returns something, otherwise a code block
of the step. ``automationv3.framework.block`` provides the helpers it uses:

``code_block(source)``
   rst that shows edn source as code.

``raw_html(html)``
   rst that embeds HTML as is.

HTML helpers
------------

:mod:`automationv3.framework.html` builds HTML in the web UI's classes, so a
rendered block matches the rest of the page:

``html.text(value)``
   A value as escaped text; keywords and literals as edn.

``html.mapping(data, caption=None)``
   A two-column table of a map's keys and values; nested maps become nested
   tables.

``html.table(headers, rows, caption=None)``
   A table with a header row.

.. code-block:: python

   def as_html(self, config):
       return ("<div><strong>Start the demo UUT</strong></div>"
               + html.mapping(config, caption="Configuration"))

Guidelines
----------

- Lead with what the step does, in words, in bold: "**Start the demo UUT**".
- Show identifiers and values in monospace (``ui-mono``).
- Escape everything that comes from the script (use ``html.text``).
- Prefer tables for structured arguments; keep a short call on one line.
- Rendering must not fail: a block that can't render a call should return
  ``None`` and let it show as code.
