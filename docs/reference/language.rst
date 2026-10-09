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
   * - ``(TBD "text")``
     - a step not written yet; true where a value is expected; a run that
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
   ``and``, ``or`` (both evaluate every argument), ``not``.

Sequences
   ``first``, ``rest``, ``cons``, ``append``, ``count``, ``list``, ``map``,
   ``take``, ``cycle``, ``range``, ``partition``, ``apply``.

Maps
   ``assoc``, ``dissoc`` (both return copies).

Predicates
   ``nil?``, ``some?``, ``number?``, ``symbol?``, ``list?``,
   ``procedure?``, ``eq?``.

Strings and output
   ``str``, ``print``.

Connectors
   ``connector``, ``group``, ``same?``, ``connector?``. See
   :doc:`../scripts/connectors`.

Literals
--------

Besides edn's, time literals: a number with a unit, ``500ms``, ``5s``,
``2min``, ``1h`` (or ``msec``, ``seconds``, ``minutes``, ``hours`` and their
like). Each is a number of seconds that is shown as written.

Dotted names
------------

A name like ``cpu1.app.mode`` that nothing defines as a whole is a path below
the connector its first part (``cpu1``) is bound to. See
:doc:`../scripts/connectors`.

Bound names
-----------

While a script runs, these are bound in addition to definitions:

- each variation symbol, to the running variation's value;
- each UUT's name (e.g. ``demo``), to its handle, if it offers one.

``wait-timeout`` and ``wait-every``, if a script or its ``core.rst`` defines
them, are Wait's defaults.
