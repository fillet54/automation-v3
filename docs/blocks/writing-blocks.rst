Writing a BuildingBlock
=======================

.. rst-class:: lead

   A BuildingBlock is a step scripts call by name: an action, an assertion or
   a value. It checks its arguments, runs, and returns what it did or found.

The smallest block
------------------

.. code-block:: python

   from automationv3.framework.block import BlockResult, BuildingBlock


   class Wait(BuildingBlock):
       """Wait a number of seconds::

           (Wait 5)
       """

       def check_syntax(self, *values):
           return len(values) == 1 and isinstance(values[0], (int, float))

       def execute(self, seconds):
           time.sleep(seconds)

Scripts call it as ``(Wait 5)``. The class name is the name scripts use;
override ``name()`` to choose another (``TableDriven`` is called as
``Table-Driven``).

The docstring and ``usage()`` are the block's documentation for script
writers; see :ref:`documenting-blocks`.

The parts of a block
--------------------

``kind``
   ``ACTION`` (the default), ``ASSERTION`` or ``VALUE``, from
   :mod:`automationv3.framework.block`. It decides what a call gives the code
   around it and how the call reads in a report:

   - an action does something; a call gives back what ``execute`` returned;
   - an assertion checks something; a call gives back ``true`` or ``false``,
     and a false one fails the step;
   - a value reads something; a call gives back the value, and the report
     shows it quietly, with what it returned.

   Only blocks fail steps: script code around them never does by its value.

``check_syntax(*values)``
   Returns true if the block accepts a call with these arguments,
   **evaluated**. Several blocks may share a name, each taking values of its
   own: the arguments are evaluated once, each block of the name is asked in
   turn, and the first that accepts the call runs it, with those values. A
   call no block accepts is an error, which says what types it was given and
   shows the block's usage.

   Since it needs the values, it runs when the call does. Before the script
   runs, the static check can only see that some block of the name takes
   that many arguments (from ``execute``'s parameters).

``check_syntax_forms(*forms)``
   The same, but on the arguments **as written**, for blocks that take them
   as written (``execute_forms``, or ``quoted`` parameters): those are asked
   this instead, and never have their arguments evaluated to be matched.
   Because it needs no values, it is checked before the script runs.

``require_unique``
   Set it to have every block of the name asked, and more than one accepting
   a call be an error (naming the blocks), rather than the first winning. For
   blocks plugins implement for their own types (see
   :ref:`implementing-value-blocks`), so two plugins can't both claim a
   value.

``abstract``
   Set on a class (it isn't inherited) that only documents a name, its usage
   and docstring, for plugins to implement by subclassing. It is never asked
   to accept a call; a call of a name only an abstract block has is an error,
   "no plugin implements it".

``execute(*args)``
   Runs the block with its arguments **evaluated**, like a function call:
   symbols, calls, and values inside maps and vectors are evaluated in the
   running script, so definitions, variation symbols and UUT handles all
   work.

``quoted``
   Parameters of ``execute`` that get their argument **as written** instead,
   for arguments that are syntax. ``Verify`` quotes its operator and gets the
   two sides evaluated:

   .. code-block:: python

      class Verify(BuildingBlock):
          kind = ASSERTION
          quoted = {"op"}

          def execute(self, actual, op=None, expected=None):
              passed = OPERATORS[str(op)](actual, expected)
              return BlockResult(passed, stdout=f"{show(actual)} {op} {show(expected)}")

``execute_forms(*forms)``
   Implement this instead of ``execute`` when every form carries meaning as
   written, for example bare symbols used as names (``Table-Driven``'s
   column headers). It gets the arguments exactly as written and **never
   evaluates them**; a block that needs some arguments evaluated quotes the
   others instead, or evaluates them itself with ``context.evaluate`` (as
   Wait does, again on every check). The static check doesn't look inside its
   arguments, unless the block lists the forms it evaluates with
   ``evaluated_forms(*forms)``.

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

   BlockResult(passed, stdout="", stderr="", value=None)

``passed``
   Whether the block passed. A falsy result fails the step, wherever the
   block was called (unless the call is inside ``try-ok?`` or ``try``).

``value``
   What the call gives the code around it. Set for you from a plain return,
   and always ``passed`` for an assertion.

``stdout``
   What the run page shows under the step: say what was checked or done,
   with the values, e.g. ``60 <= 80`` or ``started in :normal with 1
   reading(s)``. A good ``stdout`` makes a failure diagnosable from the
   report alone.

``stderr``
   Error detail.

Returning a plain value works too. For an assertion, a truthy value passes and
a falsy one fails; for an action or a value block, a plain value passes and
is what the call gives back (``None`` for an action that has nothing to say).

An exception raised from ``execute`` makes the step an **error** rather than a
failure, with its traceback shown on request, so there is no need to catch
errors only to report them. Return ``BlockResult(False, ...)`` for the case
where the system under test misbehaved, and let a broken bench raise.

``BlockResult`` is a dataclass; subclass it if a block wants to carry more
detail.

Reaching the running script
---------------------------

:mod:`automationv3.framework.context` gives a running block the script's
bindings:

``context.lookup("demo")``
   The value bound to a name: a UUT handle, a variation symbol, a
   definition.

``context.written_args()``
   The arguments of the running call, as written, e.g. to describe them in
   ``stdout``. ``Verify`` shows ``(< 2 limit) is true`` this way.

``StartDemo`` uses both: its configuration arrives evaluated, and it finds the
UUT through its handle.

.. code-block:: python

   class StartDemo(BuildingBlock):
       """Restart the demo UUT from a configuration map::

           (StartDemo {:mode :emergency
                       :readings {:brake-pressure 70}})
       """

       def check_syntax(self, *values):
           return len(values) == 1 and isinstance(values[0], dict) and MODE in values[0]

       def execute(self, config):
           demo = context.lookup("demo")
           demo.start(config[MODE])
           readings = config.get(READINGS, {})
           for name, value in readings.items():
               demo.set(name, value)
           return BlockResult(True, stdout=f"started in {edn.writes(config[MODE])} "
                                           f"with {len(readings)} reading(s)")

.. _implementing-value-blocks:

Implementing Read and the value blocks
--------------------------------------

``Read``, ``SetValue``, ``SetFixedValue`` and ``ClearFixedValue`` are abstract
(``automationv3.plugins.core.value_blocks``): the framework documents them,
and Verify and Wait use them, but only a plugin knows how to reach a value.
A plugin gives its values a kind of ref of its own, a subclass of
``framework.refs.Ref``, and implements each block for it: set ``ref_type``
and implement one method.

.. code-block:: python

   from automationv3.framework import lisp
   from automationv3.framework.refs import Ref
   from automationv3.plugins.core import value_blocks


   class Connector(Ref):
       """A connector of my system, by path"""


   lisp.global_env["connector"] = Connector        # (connector "sys.cpu1")


   class Read(value_blocks.Read):
       ref_type = Connector

       def read(self, ref):
           return my_system().read(ref.path)


   class SetValue(value_blocks.SetValue):
       ref_type = Connector

       def write(self, ref, value):
           my_system().write(ref.path, value)


   class SetFixedValue(value_blocks.SetFixedValue):
       ref_type = Connector

       def fix(self, ref, value):
           my_system().hold(ref.path, value)


   class ClearFixedValue(value_blocks.ClearFixedValue):
       ref_type = Connector

       def release(self, ref):
           my_system().release(ref.path)

Each accepts only its ``ref_type`` (or a group of only those), and each
requires a unique match, so plugins with kinds of refs of their own load side
by side. The base classes do the rest: a group's members one by one, the
record of what a run touched, and releasing whatever a script leaves fixed
when it ends. Verify, Wait and ``same?`` read refs through whichever Read
accepts them, so a plugin never overrides those. The Vehicle Manager sample
(``automationv3/plugins/vm/blocks.py``) is a worked example.

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

Blocks are plain classes: test ``check_syntax`` (with values) and ``execute``
directly, and
run a small script through the executor for the integration (see the tests in
``test/`` for examples using ``test/rvt.py``).
