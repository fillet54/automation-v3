Script language
===============

.. rst-class:: lead

   Everything a script can contain, in one place.

Directives (rst)
----------------

``.. rvt:: [title]``
   A block of script code. Options:

   ``:definitions:``
      The block only defines things; shown collapsed; only before the first
      step.

   ``:variations: name, name``
      The block applies only to these variations.

   With a title, the block's forms are collapsed under it.

``.. rvt-variant::``
   Prose and ``rvt`` blocks that apply only to some variations. Option:
   ``:variations: name, name`` (required).

``:req:`ID```
   References a requirement the script verifies.

Forms
-----

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Form
     - Kind
   * - ``(def name value)``
     - definition, top level only
   * - ``(defn name [params] body...)``
     - definition, top level only
   * - ``(uut :name)``
     - declaration
   * - ``(environments :name ...)``
     - declaration
   * - ``(import FOLDER)``
     - directive, top level only
   * - ``(variations "sym ..." ["name" [values...] ...])``
     - directive, once per script
   * - ``(Precondition "text" check [:heal ["text"] heal])``
     - precondition, before the first step
   * - anything else in a list
     - a step

Special forms
-------------

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Form
     - Meaning
   * - ``(if test then else?)``
     - conditional
   * - ``(do forms...)``
     - evaluate in order, returning the last
   * - ``(and forms...)``, ``(or forms...)``
     - evaluate left to right only until the result is decided, returning
       that value
   * - ``(let [name value ...] body...)``
     - local bindings
   * - ``(fn name? [params] body...)``
     - a function; ``(fn ([a] ...) ([a b] ...))`` for several arities
   * - ``(quote form)``, ``'form``
     - the form unevaluated; vectors, maps and sets otherwise evaluate their
       items
   * - ``(.method obj args...)``
     - call a method on a Python object
   * - ``(.-attr obj)``
     - read an attribute
   * - ``(step "title" body...)``
     - group the body's block calls under one reported entry
   * - ``(try-ok? form)``
     - true if no block call in it failed, else false; never stops the step
   * - ``(try form default)``
     - the form's value, or the default if a block call in it failed
   * - ``(TBD)``, ``(TBD "text")``
     - a step not written yet (its block's title, or the text, says what
       it will do); true where a value is expected; a run that
       reaches one is incomplete
   * - ``(quietly forms...)``
     - run forms with their block calls left out of the output

Built-in functions
------------------

Arithmetic and comparison
   ``+ - * / > < >= <= = not=`` and ``abs``, ``max``, ``min``, ``round``,
   ``expt``, and every function and constant of Python's ``math`` module
   (``sqrt``, ``pi``, ...).

Logic
   ``not``. ``and`` and ``or`` are special forms: they short-circuit.
   ``and`` returns the first falsy value or the last value; with no arguments
   it returns true. ``or`` returns the first truthy value or the last value;
   with no arguments it returns nil. Truthiness keeps the existing rules:
   nil, false, zero and empty collections are falsy.

Sequences
   ``first``, ``rest``, ``cons``, ``append``, ``count``, ``list``, ``map``,
   ``take``, ``cycle``, ``range``, ``partition``, ``apply``, ``nth``,
   ``vector``, ``vec``, ``filter``, ``reduce``.

   ``(range end)``, ``(range start end)`` and ``(range start end step)``
   return a finite EDN vector of integers, excluding ``end``. The default
   start is 0 and step is 1; negative steps are allowed, zero is an error.
   Unlike the earlier unbounded counter, ``(range)`` requires a bound and
   ``(range 5)`` is ``[0 1 2 3 4]``.

Maps
   ``assoc``, ``dissoc`` (both return copies), ``get``, ``get-in``,
   ``contains?``, ``keys``, ``vals``.

Predicates
   ``nil?``, ``some?``, ``number?``, ``symbol?``, ``list?``,
   ``procedure?``, ``eq?``.

Strings and output
   ``str``, ``print``.

Refs
   ``group``, ``same?``, ``ref?``; plugins add their own, such as the
   Vehicle Manager's ``connector``. See :doc:`../scripts/refs`.

Collection helpers
------------------

``(get collection key default?)``
   Read a map key or a nonnegative sequence index. Missing entries return
   the default, or ``nil``. Existing ``false`` and ``nil`` values are kept.

``(get-in collection [key ...] default?)``
   Follow nested map keys and sequence indexes. An empty path returns the
   original value. A missing part returns the default, or ``nil``.

``(nth collection index default?)``
   Read a zero-based sequence or iterator index. A missing index raises an
   error unless a default is supplied. Negative indexes are missing;
   booleans and noninteger indexes are errors.

``(contains? collection key)``
   Test map/set membership or whether a sequence index exists. This tests
   indexes, not sequence values: ``(contains? [10 20] 1)`` is true,
   ``(contains? [10 20] 20)`` is false.

``(keys map)``, ``(vals map)``
   Return vectors in the map's insertion order.

``(vector value ...)``, ``(vec collection)``
   Construct a vector, or copy/materialize an iterable into one. ``vec``
   on a map gives its keys. It is useful for the iterators returned by
   ``map`` and ``take``.

``(filter predicate collection)``
   Return a vector of items for which the predicate is truthy.

``(reduce function collection)``, ``(reduce function initial collection)``
   Accumulate a result. Without ``initial``, use the first item; on an empty
   collection call the function with no arguments (``(reduce + [])`` is 0).
   With ``initial``, an empty collection returns it.

``keys``, ``vals``, ``vec`` and ``filter`` return EDN vectors, not iterators,
so their results can be counted, reused and shown in reports. ``nil`` is
treated as an empty collection by those functions and by ``reduce``.

Literals
--------

Besides edn's, time literals: a number with a unit, ``500ms``, ``5s``,
``2min``, ``1h`` (or ``msec``, ``seconds``, ``minutes``, ``hours`` and their
like). Each is a number of seconds that is shown as written.

Dotted names
------------

A name like ``cpu1.app.mode`` that nothing defines as a whole is a path below
the ref its first part (``cpu1``) is bound to. See :doc:`../scripts/refs`.

Bound names
-----------

While a script runs, these are bound in addition to definitions:

- each variation symbol, to the running variation's value;
- each UUT's name (e.g. ``demo``), to its handle, if it offers one.

``wait-timeout`` and ``wait-every``, if a script or its ``core.rst`` defines
them, are Wait's defaults.
