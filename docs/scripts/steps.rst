Steps
=====

.. rst-class:: lead

   Every top-level form that isn't a definition or directive is a step. A step
   passes or fails, and a failing step stops the script.

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
     - Vectors and maps.
   * - ``(.mode demo)``
     - Calls the ``mode`` method on the ``demo`` handle; ``(.-attr obj)``
       reads an attribute.

Special forms: ``if``, ``do``, ``let``, ``fn``, ``quote``, ``def``,
``defn``, ``defblock``, ``passes?`` and ``quietly``. Built-in functions
include arithmetic and comparison (``+ - * / < <= > >= = not=``), ``and``,
``or``, ``not``, ``count``, ``first``, ``rest``, ``map``, ``str``,
``assoc``, ``dissoc`` and the functions of Python's ``math`` module. See
:doc:`../reference/language` for the full list.

How a step passes
-----------------

A block call
   ``(Verify (reading :brake-pressure) <= max-pressure)`` runs the
   ``Verify`` BuildingBlock, which decides whether it passed and what it
   prints (here ``60 <= 80``).

Anything else
   ``(brake-pressure-ok? (reading :brake-pressure))`` is evaluated, and the
   step passes if the value is truthy. The run page shows what it returned.

A step whose blocks fail
   If a step calls blocks, for example inside a ``defn``, the first failing
   block stops the step there and the step fails. See :doc:`composing`.

An exception
   An error in a step fails it, with the traceback shown under the step.

When a step fails, the remaining steps don't run.

What the run page shows
-----------------------

Each step appears as rendered in the script, with:

- a badge: :status:`passed`, :status:`failed` or :status:`error`;
- its duration, to the millisecond;
- what it printed, and any error, when expanded;
- the blocks it called, nested beneath it;
- any files its blocks attached (see :doc:`../blocks/attachments`).

Blocks available to scripts
---------------------------

The blocks you can call depend on the plugins installed. The
:doc:`blocks` lists every one, with how to call it and what it does; the
most common is :ref:`Verify <block-Verify>`.
