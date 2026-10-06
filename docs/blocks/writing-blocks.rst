Writing a BuildingBlock
=======================

.. rst-class:: lead

   A BuildingBlock is a step scripts call by name. It checks its arguments,
   runs, and returns a result that says whether it passed.

The smallest block
------------------

.. code-block:: python

   from automationv3.framework.block import BlockResult, BuildingBlock


   class Wait(BuildingBlock):
       """Wait a number of seconds::

           (Wait 5)
       """

       def check_syntax(self, *args):
           return len(args) == 1

       def execute(self, seconds):
           time.sleep(seconds)
           return BlockResult(True)

Scripts call it as ``(Wait 5)``. The class name is the name scripts use;
override ``name()`` to choose another (``TableDriven`` is called as
``Table-Driven``).

The docstring and ``usage()`` are the block's documentation for script
writers; see :ref:`documenting-blocks`.

The parts of a block
--------------------

``check_syntax(*args)``
   Returns true if the block accepts these arguments, as written. Several
   blocks may share a name; the first whose ``check_syntax`` accepts the call
   handles it. A call no block accepts fails with "No BuildingBlock matches".

``execute(*args)``
   Runs the block with its arguments **evaluated**, like a function call:
   symbols, calls, and values inside maps and vectors are evaluated in the
   running script, so definitions, variation symbols and UUT handles all
   work.

``execute_forms(*forms)``
   Implement this instead of ``execute`` when the forms themselves carry
   meaning, for example an operator, or bare symbols used as names. It gets
   the arguments exactly as written. ``Verify`` does this, because its
   operator is syntax:

   .. code-block:: python

      def execute_forms(self, *forms):
          actual, op, expected = forms
          actual_value = context.evaluate(actual)
          expected_value = context.evaluate(expected)
          passed = OPERATORS[str(op)](actual_value, expected_value)
          return BlockResult(passed, stdout=f"{show(actual_value)} {op} {show(expected_value)}")

``as_html(*forms)`` / ``as_rst(*forms)``
   How a step using the block reads in a rendered script. See
   :doc:`rendering`.

``usage()``
   How scripts call the block. See :ref:`documenting-blocks`.

.. _documenting-blocks:

Documenting a block
-------------------

A block documents itself, and the :doc:`../scripts/blocks` is generated from
every block the plugins define. Two things go into its entry:

``usage()``
   How scripts call the block, as a string, one call per line:

   .. code-block:: python

      def usage(self):
          return "(Verify actual op expected)\n(Verify value)"

   Write parameters as names, ``name?`` for an optional one, and ``name ...``
   for repeats, with the brackets and braces of the shape the block expects
   (``"(StartDemo {:mode mode :readings {name value ...}})"``). By default it
   is the block's name followed by the parameters of ``execute`` (or
   ``execute_forms``), so ``def execute(self, seconds)`` gives
   ``(Wait seconds)``; override it whenever that doesn't show the shape.

The class docstring
   What the block does, written in reStructuredText: a one-line summary,
   then what each parameter means, what the step prints, and an example.
   Anything rst can do works, notes and tables included.

   .. code-block:: python

      class SnapshotDemo(BuildingBlock):
          """Attach the demo UUT's state to the run as ``<label>.json``.

          The file holds the installed version, mode, readings and faults, and
          is listed with the step on the run page.

          Example::

              (SnapshotDemo "after-braking")
          """

   Literal blocks (``::``) are highlighted as script code. A block with no
   docstring of its own is listed as not documented yet.

The documentation is rendered with the ``building-blocks`` directive, which
any page can use; give it a plugin package to list just that plugin's blocks:

.. code-block:: rst

   .. building-blocks:: automationv3.plugins.sample

Results
-------

Return a :class:`~automationv3.framework.block.BlockResult`:

.. code-block:: python

   BlockResult(passed, stdout="", stderr="")

``passed``
   Whether the block passed. A falsy result fails the step (or, inside a
   ``defblock``, is reported as a failed nested call).

``stdout``
   What the run page shows under the step: say what was checked or done,
   with the values, e.g. ``60 <= 80`` or ``started in :normal with 1
   reading(s)``. A good ``stdout`` makes a failure diagnosable from the
   report alone.

``stderr``
   Error detail.

Returning a plain value works too: truthy passes, falsy fails. An exception
raised from ``execute`` fails the step with its traceback in ``stderr``, so
there is no need to catch errors only to report them.

``BlockResult`` is a dataclass; subclass it if a block wants to carry more
detail.

Reaching the running script
---------------------------

:mod:`automationv3.framework.context` gives a running block the script's
bindings:

``context.lookup("demo")``
   The value bound to a name: a UUT handle, a variation symbol, a
   definition.

``context.evaluate(form)``
   Evaluates a form in the running script, including inside maps and
   vectors. Use it from ``execute_forms`` to evaluate the arguments that are
   values.

``StartDemo`` uses both: its configuration arrives evaluated, and it finds the
UUT through its handle.

.. code-block:: python

   class StartDemo(BuildingBlock):
       """Restart the demo UUT from a configuration map::

           (StartDemo {:mode :emergency
                       :readings {:brake-pressure 70}})
       """

       def check_syntax(self, *args):
           return len(args) == 1 and isinstance(args[0], dict) and MODE in args[0]

       def execute(self, config):
           demo = context.lookup("demo")
           demo.start(config[MODE])
           readings = config.get(READINGS, {})
           for name, value in readings.items():
               demo.set(name, value)
           return BlockResult(True, stdout=f"started in {edn.writes(config[MODE])} "
                                           f"with {len(readings)} reading(s)")

edn values in Python
--------------------

Arguments arrive as edn values from :mod:`automationv3.framework.edn`:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - edn
     - Python
   * - ``:mode``
     - ``edn.Keyword`` (a ``str`` subclass; compare with ``edn.Keyword("mode")``)
   * - ``demo``
     - ``edn.Symbol`` (a ``str`` subclass)
   * - ``"text"``
     - ``str``
   * - ``60``, ``1.5``
     - ``int``, ``float``
   * - ``(a b)``, ``[a b]``
     - ``edn.List``, ``edn.Vector`` (``list`` subclasses)
   * - ``{:a 1}``, ``#{1 2}``
     - ``edn.Map`` (a ``dict``), ``edn.Set``
   * - ``true``, ``nil``
     - ``True``, ``None``

``edn.writes(value)`` writes a value back as edn, which is the clearest way
to show values in ``stdout``.

Testing a block
---------------

Blocks are plain classes: test ``check_syntax`` and ``execute`` directly, and
run a small script through the executor for the integration (see the tests in
``test/`` for examples using ``test/rvt.py``).
