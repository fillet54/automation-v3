Steps
=====

.. rst-class:: lead

   Every top-level form that isn't a definition or directive is a step. Only
   blocks fail steps, and a failing step stops the script.

The language in brief
---------------------

Script code is `edn <https://github.com/edn-format/edn>`_ evaluated as a small
Lisp, close to Clojure:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Form
     - Meaning
   * - ``60``, ``"text"``, ``true``, ``nil``
     - Literals evaluate to themselves.
   * - ``:brake-pressure``
     - Keywords evaluate to themselves; use them as names and map keys.
   * - ``max-pressure``
     - Symbols are looked up: definitions, variation symbols, UUT handles.
   * - ``(f a b)``
     - A call: ``f`` is a function, a block or a special form.
   * - ``[1 2 3]``, ``{:mode :normal}``
     - Vectors and maps; their items are evaluated, so ``[limit (+ 1 2)]``
       is ``[80 3]``. Write ``'[a b]`` for data exactly as written.
   * - ``(.mode demo)``
     - Calls the ``mode`` method on the ``demo`` handle; ``(.-attr obj)``
       reads an attribute.

Special forms: ``if``, ``do``, ``let``, ``fn``, ``quote``, ``def``,
``defn``, ``step``, ``try-ok?``, ``try`` and ``quietly``. Built-in functions
include arithmetic and comparison (``+ - * / < <= > >= = not=``), ``and``,
``or``, ``not``, ``count``, ``first``, ``rest``, ``map``, ``str``,
``assoc``, ``dissoc`` and the functions of Python's ``math`` module. See
:doc:`../reference/language` for the full list.

Actions, assertions and values
------------------------------

Every block is one of three kinds:

Actions
   do something to the system: ``(StartDemo {:mode :normal})``,
   ``(SetValue bench.sun false)``. An action fails if it can't do it.

Assertions
   check something: ``(Verify (reading :brake-pressure) <= max-pressure)``,
   ``(Wait nav.mode = :run :within 5s)``. An assertion fails when its check
   comes out false.

Values
   read something and give it back, to use in other forms. A value block
   fails if it can't read it.

Called inside other code, an assertion gives ``true`` or ``false``, and an
action or a value gives what it returned.

How a step passes
-----------------

**Only blocks fail steps.** A step passes unless a block it called failed,
or something raised. Its value is shown on the run page, but never judged:

.. code-block:: clojure

   (brake-pressure-ok? 40)            ; passes whatever it returns
   (Verify (brake-pressure-ok? 40))   ; fails if it returns false

To check a value, assert it. The static check warns about a step whose value
is all it does, like ``(- 10 10)`` or ``(= a b)``: it can never fail.

A block call
   ``(Verify (reading :brake-pressure) <= max-pressure)`` runs the
   ``Verify`` BuildingBlock, which decides whether it passed and what it
   prints (here ``60 <= 80``).

Blocks called inside other code
   If a step calls blocks, for example inside a ``defn``, the first failing
   block stops the step there and the step fails, wherever the call is. See
   :doc:`composing` for grouping calls and suppressing failures.

Fail or error
   A step **fails** when an assertion comes out false, or an action or value
   reports it couldn't do its job: the system under test misbehaved. It
   **errs** when something raises: a block, or the script's own code (a
   division by zero, a bad method call). The run's outcome says which.

When a step fails or errs, the remaining steps don't run.

Before anything runs
--------------------

Definitions only appear at the top level, so every name a script uses is
known before it runs. When a script is viewed or queued, it is checked
statically, once per variation: unknown names (with a suggestion), names used
before they are defined, calls with the wrong number of arguments, block calls
no form of the block accepts, and definitions inside other forms. These are
errors, shown by the statement they are about, and a script with errors
can't be queued. Shadowing a block, a builtin or a ``core.rst`` definition,
and a step whose value is thrown away, are warnings.

What the run page shows
-----------------------

Each step appears as rendered in the script, with:

- a badge: :status:`passed`, :status:`failed` or :status:`error`;
- its duration, to the millisecond;
- what it printed;
- for a failure, why, and the code it happened at, with the offending form
  marked, then each call that led there (across ``core.rst`` files too);
  for an error, the traceback on request;
- the blocks it called, nested beneath it;
- any files its blocks attached (see :doc:`../blocks/attachments`).

Blocks available to scripts
---------------------------

The blocks you can call depend on the plugins installed. The
:doc:`blocks` lists every one, with how to call it and what it does; the
most common is :ref:`Verify <block-Verify>`.
