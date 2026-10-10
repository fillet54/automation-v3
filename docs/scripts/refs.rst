Refs and values
===============

.. rst-class:: lead

   A ref names a value somewhere else, such as a point of the system under
   test or an input of the bench, so blocks can read, wait on and drive it.
   Scripts name a few roots once and reach everything below them with dotted
   names.

Declaring refs
--------------

Each plugin has its own kind of ref, and a function to make one; the
Vehicle Manager's are connectors. Declare the roots a system's tests use in
its top-level ``core.rst`` (or a script's definitions section):

.. code-block:: clojure

   (def cpu1 (connector "sys.cpu1"))
   (def cpu2 (connector "sys.cpu2"))
   (def nav cpu1.app.nav)

Anything below a ref is reached with a dotted name: ``cpu1.app.nav.mode``
refers to ``sys.cpu1.app.nav.mode``, and ``nav.mode`` to the same value. A
``def`` gives a deep path a short name; reports call a ref by the name the
script used (``nav.mode``) and show its full path beside it.

Refs pass like any other value: to a ``defn``, in a table row, in a
variation. A dotted name works on whatever is bound to a ref:

.. code-block:: clojure

   (defn check-nav [sys]
     (Verify sys.app.nav.mode = :run))

   (check-nav cpu2)

Static analysis checks the first part of every dotted name before anything
runs: ``cpuu.app.mode`` is an error (``unknown name cpuu``) when nothing
defines ``cpuu``. What's below a root is the system's to say, when the script
runs.

Groups
------

A group is several refs tested together, such as redundant units or a left
and a right side:

.. code-block:: clojure

   (def cpu (group cpu1 cpu2))

``cpu.app.nav.mode`` is that path on every member. Members keep their own
names, so results say which one disagreed. Reach one member by its own name,
``cpu1.app.nav.mode``.

Reading and writing
-------------------

``(Read nav.mode)``
   The value a ref points at. For a group, a map of member name to value:
   ``{:cpu1 :run, :cpu2 :run}``.

``(SetValue bench.sun false)``
   Writes a value, once. The system may change it afterwards.

``(SetFixedValue bench.attitude-error 15.0)``
   Holds a value until ``(ClearFixedValue bench.attitude-error)``. Whatever a
   script leaves fixed is released when it ends, however it ends, and the run
   lists each release under *Cleanup*. A release that fails makes the run an
   error.

On a group, each writes every member. The plugin that made the ref does the
reading and writing: each implements these blocks for its own kind of ref
(see :ref:`implementing-value-blocks`).

Verify
------

Either side of a check can be a ref, which is read for the check:

.. code-block:: clojure

   (Verify nav.mode = :run)
   (Verify cpu1.cmd = cpu2.echo)
   (Verify nav.ready)                     ; truthy

On a group, ``Verify`` checks every member, and all have to pass;
``VerifyAll`` is the same block by another name. ``VerifyAny`` passes if any
member does. A group against a single value, or a single ref, compares each
member with it; a group against a group pairs members in order, and the two
need as many members.

.. code-block:: clojure

   (Verify cpu.app.nav.mode = :run)       ; both
   (VerifyAny cpu.role = :primary)        ; at least one
   (Verify left.cmd = right.echo)         ; left's members with right's, in order
   (Verify (same? cpu.app.nav.solution))  ; members agree with each other

The step shows each comparison with the value read, one per member, marking
the ones that didn't hold:

.. code-block:: text

   cpu1.role (:primary) = :primary
   cpu2.role (:backup) = :primary  <- no

Wait
----

``Wait`` checks the same way, again and again, until the check holds or time
runs out, which fails the step:

.. code-block:: clojure

   (Wait nav.mode = :run :within 5s)
   (Wait eps.soc >= 80.0 :within 3h :every 1min)
   (Wait (Telemetry :mode) = :safe :within 2min)

``:within`` is how long to wait. Without it, the time is ``wait-timeout`` if
the script (or its ``core.rst``) defines it, otherwise 10 s. ``:every`` is how
often to check: by default ``wait-every``, otherwise 100 ms. Block calls in the
check run each time without being reported, so polling doesn't flood the
report; the step says how long it took (``after 61s: ...``) or what it last
saw.

On a group, ``Wait`` (and ``WaitAll``) need every member to hold at once;
``WaitAny`` needs one; ``WaitSame`` waits for the members to agree:

.. code-block:: clojure

   (WaitAll cpu.app.nav.mode = :run :within 10s)
   (WaitAny cpu.role = :primary :within 30s)
   (WaitSame cpu.app.nav.solution :within 5s)

Given only a time, ``Wait`` waits that long: ``(Wait 2s)``.

Time
----

Times are seconds. They can be written with a unit: ``500ms``, ``5s``,
``2min``, ``1h``, or spelled out, ``5seconds``, ``2minutes``. ``5000ms`` and
``5s`` are the same value, 5.0, and both are shown as written.

A run keeps time by its environment's clock: the wall clock on hardware, the
simulation's in a simulated environment, so a Wait on the simulated Vehicle
Manager runs the platform forward while it polls. See
:doc:`../blocks/uuts-and-environments`.

What a run touched
------------------

Every run records the refs it read, set, fixed or cleared. A run's page lists
them under *Values touched*, with the steps that touched each; a report's
page rolls them up across its latest runs, with the scripts and requirements
that touched each.
