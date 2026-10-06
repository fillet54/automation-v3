Variations
==========

.. rst-class:: lead

   Run one script several ways. Each variation binds the same symbols to its
   own values, and parts of the document can apply to only some variations.

Declaring variations
--------------------

A script declares its variations once, with the symbols they bind and one row
per variation: a display name and the values.

.. code-block:: clojure

   (variations "mode pressure"
     ["normal"    [:normal 60]
      "limp-home" [:limp-home 75]
      "emergency" [:emergency max-pressure]])

Here every run binds ``mode`` and ``pressure``. The ``emergency`` variation
uses ``max-pressure`` from the ``core.rst`` chain: values are kept as forms
and evaluated when the script runs, so they can use definitions.

Each variation runs as its own job, so a script with three variations in two
environments queues six runs, and the report rolls them up together.

Choosing variations to run
--------------------------

By default every variation runs. When queuing you can untick variations, or
filter them with an edn predicate over the variation symbols plus ``name`` and
``index``:

.. code-block:: clojure

   (not= mode :emergency)

From the command line use ``--variation NAME`` (repeatable) or
``--filter EXPR``.

Blocks for some variations
--------------------------

An ``rvt`` block with ``:variations:`` only applies to the variations it
names, by display name, comma-separated. Other variations skip it entirely.

.. code-block:: rst

   .. rvt::
      :variations: emergency

      (Verify (reading :brake-pressure) = max-pressure)

.. _scoped-definitions:

Overriding definitions per variation
------------------------------------

Definitions blocks take ``:variations:`` too. The last definition of a name
that applies to the running variation wins, so a default followed by an
override reads naturally:

.. code-block:: rst

   .. rvt::
      :definitions:

      (def headroom 15)

   .. rvt::
      :definitions:
      :variations: limp-home

      (def headroom 5)

``limp-home`` runs with a headroom of 5; the others with 15. When a single
variation is selected in the script view, the definitions are rolled up into
the values that variation actually uses.

Prose and code for some variations: ``rvt-variant``
---------------------------------------------------

To explain a variation-specific part of a test, wrap the prose and its blocks
in ``.. rvt-variant::``:

.. code-block:: rst

   .. rvt-variant::
      :variations: emergency

      In emergency mode the pressure runs right at the limit, and must stay
      there.

      .. rvt:: Pressure holds at the limit

         (Verify (reading :brake-pressure) = max-pressure)

Every ``rvt`` block inside applies to the variant's variations. An inner block
may narrow that further with its own ``:variations:``, but may not name a
variation outside the variant.

How the script view shows variations
------------------------------------

The selector under the breadcrumbs defaults to **All**. With **All**, the page
shows everything, and blocks limited to some variations say so ("Only for
emergency"). Selecting one variation hides everything that doesn't apply to it
and rolls definitions up, so the page reads as exactly the test that variation
runs. The selection is kept in the URL, so you can link to it.

**Details** lists the variations as a table of their values.

Rules
-----

- A script declares ``variations`` at most once, and not in a ``core.rst``.
- ``:variations:`` names must be declared by the script.
- Blocks limited to variations can't contain declarations (``uut``,
  ``environments``, ``variations``, ``import``).
- ``core.rst`` blocks can't be limited to variations.
