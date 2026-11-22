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
   * - ``(let [pattern value ...] body...)``
     - local bindings; each pattern is a name or takes the value apart (see
       `Destructuring`_)
   * - ``(fn name? [params] body...)``
     - a function; ``(fn ([a] ...) ([a b] ...))`` for several arities.
       ``[a & more]`` takes the arguments after ``a`` as a list (empty
       when there are none); parameters are patterns too. A named fn can
       call itself by its name.
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

   These are eager: ``map``, ``filter``, ``take``, ``rest``, ``cons``,
   ``partition``, ``vec`` and ``range`` return EDN vectors, which can be counted, indexed
   and read more than once. ``cycle`` alone is endless; bound it with
   ``take`` before passing it to anything else.

   ``(range end)``, ``(range start end)`` and ``(range start end step)``
   return a finite EDN vector of integers, excluding ``end``. The default
   start is 0 and step is 1; negative steps are allowed, zero is an error.
   Unlike the earlier unbounded counter, ``(range)`` requires a bound and
   ``(range 5)`` is ``[0 1 2 3 4]``.

Maps
   ``assoc``, ``dissoc`` (both return copies), ``get``, ``get-in``,
   ``contains?``, ``keys``, ``vals``. ``get`` takes a map's key, a set's
   member or a sequence's index, and gives nil (or a default) when missing.

Predicates
   ``nil?``, ``some?``, ``number?``, ``symbol?``, ``list?``,
   ``procedure?``, ``eq?``.

Strings and output
   ``str``, ``print``, ``println``. What a step prints is its output: the
   run page shows it with the step, and the editor's console under it.
   ``print`` writes its values separated by spaces, strings as they are
   and anything else as edn; ``println`` ends with a new line. A Wait's
   repeated checks print nothing.

Refs
   ``group``, ``same?``, ``ref?``; plugins add their own, such as the
   lunar module's ``connector``. See :doc:`../scripts/refs`.

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

Destructuring
-------------

Wherever ``let``, ``fn`` and ``defn`` bind a name they take a pattern, as in
Clojure, and patterns nest:

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - Pattern
     - Binds
   * - ``[a b]``
     - the first two items; missing items, or a nil value, give nil
   * - ``[a & more]``
     - ``more`` to the rest as a list, empty when nothing is left
   * - ``[a b :as all]``
     - ``all`` to the whole value
   * - ``{a :a, [x y] :pos}``
     - each pattern to the value under its key
   * - ``{:keys [a b]}``
     - ``a`` and ``b`` to the values under ``:a`` and ``:b``. ``:strs`` and
       ``:syms`` are the same, as keywords equal strings here
   * - ``{:keys [a] :or {a 1}}``
     - a default for a key the map lacks (not one that holds nil); it may
       use earlier names
   * - ``{:keys [a] :as m}``
     - ``m`` to the whole map

A map pattern reads a sequence as key value pairs, so ``& {:keys [scale]}``
takes keyword arguments::

    (defn scaled [x & {:keys [scale] :or {scale 1}}] (* x scale))
    (scaled 2 :scale 3)   ; 6

A function has at most one arity with ``& rest``, and no fixed arity of it
takes more arguments than that one does before ``&``. Parameters can't use
``:as``.

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
- each UUT's name (e.g. ``lm``), to its handle, if it offers one.

``wait-timeout`` and ``wait-every``, if a script or its ``core.rst`` defines
them, are Wait's defaults.
