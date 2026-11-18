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

   (variations "mission start"
     ["standard from PDI"       [:standard :pdi]
      "standard from high gate" [:standard :high-gate]
      "extended from PDI"       [:extended :pdi]
      "extended from high gate" [:extended :high-gate]])

Here every run binds ``mission`` and ``start``. Values are kept as forms
and evaluated when the script runs, so they can use definitions from the
``core.rst`` chain too.

Each variation runs as its own job, so a script with three variations in two
environments queues six runs, and the report rolls them up together.

Variation or table?
-------------------

A variation is a separate run. Use one when a case needs the unit restarted or
set up differently: a hardware configuration (an extended lunar module's
bigger tanks), a different load (its mission's erasable memory), a different
starting point, or an event that can't be undone within a run (an abort
ends the flight). Each variation is queued, run, reported and rolled up on
its own.

A variation is not a version. The version is what is installed, the UUT's
software (here, a Luminary rope); a variation is how one run sets it up. A
precondition checks the unit is set up the variation's way, and its heal
boots it so, which lets runs of the same variation reuse a unit already set
up (see :doc:`preconditions`).

When the cases can run one after the other on the unit as it is, use a
**table** instead: an ``rvt`` block with the ``:table:`` option runs its steps
once per row, in the same run. Its first form names the symbols and gives the
rows, shaped like variations:

.. code-block:: rst

   .. rvt:: Each commanded transition
      :table:

      ("extra-amps caution warning"
        ["normal"   [0   false false]
         "heavy"    [200 true  false]
         "overload" [300 true  true]])

      (SetFixedValue bench.bus-load-amps extra-amps)
      (RunFor 60)
      (Verify cwea.light.battery = caution)
      (Verify cwea.warning = warning)
      (ClearFixedValue bench.bus-load-amps)

The script page shows the rows as a table above the steps. The run page shows
each row with its steps' results. A failing row stops only itself: the other
rows still run, so one run shows every failing case, and the block, and so the
script, fails at the end. The row symbols are bound only within the block, and
a table block can't hold definitions, directives or preconditions.

A script can use both: variations for the setups that need their own runs, and
tables for the cases each setup runs through.

Choosing variations to run
--------------------------

By default every variation runs. When queuing you can untick variations, or
filter them with an edn predicate over the variation symbols plus ``name`` and
``index``:

.. code-block:: clojure

   (= mission :extended)

From the command line use ``--variation NAME`` (repeatable) or
``--filter EXPR``.

Blocks for some variations
--------------------------

An ``rvt`` block with ``:variations:`` only applies to the variations it
names, by display name, comma-separated. Other variations skip it entirely.

.. code-block:: rst

   .. rvt::
      :variations: extended from PDI, extended from high gate

      (Verify truth.downrange > -6000)

.. _scoped-definitions:

Overriding definitions per variation
------------------------------------

Definitions blocks take ``:variations:`` too. The last definition of a name
that applies to the running variation wins, so a default followed by an
override reads naturally:

.. code-block:: rst

   .. rvt::
      :definitions:

      (def approach-deg 16)

   .. rvt::
      :definitions:
      :variations: extended

      (def approach-deg 25)

``extended`` checks for a 25° approach; the others for 16°. When a single
variation is selected in the script view, the definitions are rolled up into
the values that variation actually uses.

Prose and code for some variations: ``rvt-variant``
---------------------------------------------------

To explain a variation-specific part of a test, wrap the prose and its blocks
in ``.. rvt-variant::``:

.. code-block:: rst

   .. rvt-variant::
      :variations: extended

      The extended approach comes in steeper, so from high gate the landing
      site is closer as well as lower.

      .. rvt:: Closer at high gate

         (Verify truth.downrange > -6000)

Every ``rvt`` block inside applies to the variant's variations. An inner block
may narrow that further with its own ``:variations:``, but may not name a
variation outside the variant.

How the script view shows variations
------------------------------------

The selector under the breadcrumbs defaults to **All**. With **All**, the page
shows everything, and blocks limited to some variations say so ("Only for
extended"). Selecting one variation hides everything that doesn't apply to it
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
