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
override ``name()`` to choose another, e.g. one that isn't a Python
identifier (a ``TableDriven`` class called as ``Table-Driven``).

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
   for arguments that are syntax. A block comparing two values could quote
   its operator and get the two sides evaluated:

   .. code-block:: python

      class Compare(BuildingBlock):
          kind = ASSERTION
          quoted = {"op"}

          def execute(self, actual, op, expected):
              passed = OPERATORS[str(op)](actual, expected)
              return BlockResult(passed, stdout=f"{show(actual)} {op} {show(expected)}")

``execute_forms(*forms)``
   Implement this instead of ``execute`` when every form carries meaning as
   written, for example bare symbols used as names (a table block's column
   headers). It gets the arguments exactly as written and **never
   evaluates them**; a block that needs some arguments evaluated quotes the
   others instead, or evaluates them itself with ``context.evaluate`` (as
   Wait does, again on every check). The static check doesn't look inside its
   arguments, unless the block lists the forms it evaluates with
   ``evaluated_forms(*forms)``.

``as_rst(*forms)``, ``as_result_rst(result, *forms)``
   How a step using the block reads in a rendered script, and what came of
   it in a run. See :doc:`rendering`.

``usage()``
   How scripts call the block. See :ref:`documenting-blocks`.

How a call runs
---------------

.. mermaid::
   :caption: A call of a block that implements execute. One taking its arguments as written is matched by check_syntax_forms instead

   flowchart TB
     call["A call: (Name args…)"] --> evaluate["Evaluate the arguments<br/>in the running script"]
     evaluate --> ask["Ask each block of the name:<br/>check_syntax(*values)"]
     ask -- none accepts --> nomatch["error: the types it was given,<br/>and the block's usage"]:::danger
     ask -- "the first accepts<br/>(exactly one, with require_unique)" --> execute["execute(*values)"]
     execute -- raises --> raised[The step errs]:::danger
     execute -- returns --> result["BlockResult<br/>passed, stdout, stderr, value"]
     result -- passed --> value["The call gives its value<br/>to the code around it"]:::success
     result -- not passed --> failed["The step fails<br/>(unless in try-ok? or try)"]:::warning

.. _documenting-blocks:

Documenting a block
-------------------

A block documents itself, and the :doc:`../scripts/blocks` is generated from
every block the plugins define. Two things go into its entry:

``usage()``
   How scripts call the block, as a string, one call per line:

   .. code-block:: python

      def usage(self):
          return "(Verify actual predicate args...)\n(Verify value)"

   Write parameters as names, ``name?`` for an optional one, and ``name ...``
   for repeats, with the brackets and braces of the shape the block expects
   (``"(StartLM {:mission m :start s :crew c :seed n})"``). By default it
   is the block's name followed by the parameters of ``execute`` (or
   ``execute_forms``), so ``def execute(self, seconds)`` gives
   ``(Wait seconds)``; override it whenever that doesn't show the shape.

The class docstring
   What the block does, written in reStructuredText: a one-line summary,
   then what each parameter means, what the step prints, and an example.
   Anything rst can do works, notes and tables included.

   .. code-block:: python

      class AttachTrajectory(BuildingBlock):
          """Attach the flight so far to the run: ``<label>.csv`` (one row a
          second: time, downrange, altitude, velocities, throttle, program,
          propellant) and ``<label>.svg``, a plot of the descent.

          Example::

              (AttachTrajectory "descent")
          """

   Literal blocks (``::``) are highlighted as script code. A block with no
   docstring of its own is listed as not documented yet.

The documentation is rendered with the ``building-blocks`` directive, which
any page can use; give it a plugin package to list just that plugin's blocks:

.. code-block:: rst

   .. building-blocks:: automationv3.plugins.apollo

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
   with the values, e.g. ``deca.throttle (92.5) = 92.5`` or ``reached
   :high-gate at 562 s``. A good ``stdout`` makes a failure diagnosable from the
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

``context.lookup("lm")``
   The value bound to a name: a UUT handle, a variation symbol, a
   definition.

``context.written_args()``
   The arguments of the running call, as written, e.g. to describe them in
   ``stdout``. ``Verify`` shows ``(< 2 limit) is true`` this way.

``context.check_stopped()``
   Raises ``context.Stopped`` if whatever runs the script asked it to stop
   (the editor's console has a **Stop**). The clock's sleep checks it, so a
   block that waits with ``clock.current().sleep`` stops at once; a block
   with a loop of its own of any length calls it in the loop. The lunar
   module's ``run_for`` and ``fly_to`` do, for ``lms``.

``StartLM`` uses the first: its configuration arrives evaluated (variation
symbols and definitions already replaced by their values), and it finds the
lunar module through its handle.

.. code-block:: python

   class StartLM(BuildingBlock):
       """Boot the lunar module from a configuration map::

           (StartLM {:mission :extended :start :high-gate})
       """

       def check_syntax(self, *values):
           return len(values) == 1 and isinstance(values[0], dict)

       def execute(self, config):
           lm = context.lookup("lm")
           if lm.boot(config) == edn.Keyword("rejected-load"):
               return BlockResult(False, stdout=f"{lm.version()} rejected the erasable load")
           return BlockResult(True, stdout=f"booted: {edn.writes(lm.config())}")

.. _implementing-value-blocks:

Implementing Read and the value blocks
--------------------------------------

``Read``, ``SetValue``, ``SetFixedValue`` and ``ClearFixedValue`` are abstract
(``automationv3.framework.value_blocks``): the framework documents them,
and Verify and Wait use them, but only a plugin knows how to reach a value.
A plugin gives its values a kind of ref of its own, a subclass of
``framework.refs.Ref``, and implements each block for it: set ``ref_type``
and implement one method.

.. code-block:: python

   from automationv3.framework import value_blocks
   from automationv3.framework.refs import Ref


   class Connector(Ref):
       """A connector of my system, by path"""


   # In the plugin package's __init__.py:
   def register(registry):
       registry.function("my-system/connector", Connector)


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
accepts them, so a plugin never overrides those. The lunar module's connectors
(``automationv3/plugins/apollo/blocks.py``) are a worked example.

The editor says what a ref is without running anything: hovering
``nav.time`` after ``(def cpu1 (my-system/connector "sys.cpu1"))`` and
``(def nav cpu1.app.nav)`` shows a Connector at ``sys.cpu1.app.nav.time``.
It knows a function makes refs when the function is the kind of ref itself,
as above. A function that wraps the class says so:

.. code-block:: python

   from automationv3.framework import refs


   @refs.constructs(Connector)
   def make_connector(path):
       return Connector(path)

A kind of ref can also say what is below a path, so the editor completes
paths as they are typed (``nav.`` offers ``time``, ``mode`` ...) and warns
about one that doesn't exist before anything runs. Give the class a
``children`` classmethod that answers from whatever the plugin has offline,
an ICD or a symbol table, never by reaching the system:

.. code-block:: python

   from automationv3.framework.refs import Child, Ref


   class Connector(Ref):
       @classmethod
       def children(cls, path):
           """The names directly below `path` ("" for the top)"""
           return [Child(name, leaf=point.is_value, detail=point.type_name,
                         doc=point.description)
                   for name, point in my_icd().below(path)]

``children`` returns ``None`` when it can't say (the default, so a kind of
ref without it gets no completion and no warnings), and ``[]`` for a path
that doesn't exist. ``detail`` is a word or two shown beside the name, and
``doc`` a sentence shown when hovering it.

edn values in Python
--------------------

Arguments arrive as edn values from :mod:`automationv3.framework.edn`:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - edn
     - Python
   * - ``:mission``
     - ``edn.Keyword`` (a ``str`` subclass; compare with ``edn.Keyword("mission")``)
   * - ``lm``
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
