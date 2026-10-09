UUTs and environments
=====================

.. rst-class:: lead

   A UUT plugin knows how to list, install and start a unit under test, and
   gives scripts a handle to it. An environment plugin describes where it
   runs.

Environments
------------

Subclass :class:`~automationv3.framework.uut.Environment` and set ``name``:

.. code-block:: python

   class Sim(Environment):
       """A simulated environment rooted in a work directory"""

       name = "sim"

       def __init__(self, workdir=None, **params):
           super().__init__(workdir=workdir, **params)
           self.workdir = Path(workdir or default_workdir())

       def fingerprint(self):
           return {
               "environment": self.name,
               "platform": platform.platform(),
               "python": platform.python_version(),
           }

Scripts declare where they can run with ``(environments :sim :bench)``.

A worker creates one instance per environment it hosts, passing the
parameters from its config file:

.. code-block:: json

   {
     "environments": {
       "sim": {"workdir": "/var/lib/automation/sim"},
       "bench": {}
     }
   }

``fingerprint()``
   Facts about the environment that can affect results: tool versions, rig
   serial numbers, calibration dates, firmware of attached hardware. Return a
   JSON-serializable dict. The worker adds the framework's own version and
   commit. The fingerprint is hashed into every run's identity, and a rerun is
   refused if no live environment's fingerprint matches the original
   (:doc:`../operating/configuration-management`). Include everything that
   matters and nothing that changes on its own (no timestamps).

UUTs
----

Subclass :class:`~automationv3.framework.uut.UUT` and set ``name``:

.. code-block:: python

   class Demo(UUT):
       name = "demo"

       def list_versions(self):
           return [Version(id, digest_of(id)) for id in self.VERSIONS]

       def installed_version(self, env):
           ...

       def install(self, version, env):
           ...

       def start(self, version, env):
           ...

       def handle(self, version, env):
           return DemoHandle(self, env)

Scripts declare what they test with ``(uut :demo)``.

``list_versions()``
   Every installable :class:`~automationv3.framework.uut.Version`, oldest
   first. The server calls it to offer versions when queuing; the newest is
   the default. A ``Version`` has an ``id`` (what people pick) and a
   ``digest`` that identifies the exact bits, e.g. a SHA-256 of the image.

``installed_version(env)``
   The version installed in ``env`` now, or ``None``. Workers use it to
   decide whether a job can run warm.

``install(version, env)``
   Install a version. Called in force mode when the installed version differs
   from the job's; the worker then checks ``installed_version`` again and
   fails the job if the install didn't take.

``start(version, env)``
   Start the UUT fresh. Called in force mode, after install.

``handle(version, env)``
   The object scripts use to reach the UUT, bound to the UUT's name. Return
   ``None`` if scripts don't talk to it directly.

Handles
-------

A handle is any Python object. Scripts call its methods with the dot form, so
design it as the vocabulary scripts speak:

.. code-block:: clojure

   (.mode demo)                     ; -> :normal
   (.set demo :brake-pressure 60)
   (.has_fault demo :overheat)

Guidelines for handles:

- Return edn-friendly values (keywords, numbers, strings, vectors), so
  scripts can compare them directly.
- Make actions return ``True``, so a call can be used directly as a step.
- Keep them small and well named. Wrap them in ``core.rst`` functions
  (``reading``, ``set-reading``) to give scripts a readable vocabulary, and
  put anything substantial into blocks.

Serving connectors
------------------

A handle that serves connectors (see :doc:`../scripts/connectors`) has these
methods, which the Read, SetValue, SetFixedValue, ClearFixedValue, Verify and
Wait blocks call with the connector's full path:

``read_connector(path)``
   The value at the path. Raise if there is no such connector.

``set_connector(path, value)``
   Write it once.

``fix_connector(path, value)`` and ``clear_connector(path)``
   Hold it at a value, and release it. The framework releases whatever a
   script leaves fixed when the script ends.

``connector_clock()`` and ``connector_sleep(seconds)``, optional
   The UUT's own time, for one whose time isn't the wall clock's, such as a
   simulation that only moves when run forward. Wait uses them to measure
   ``:within`` and to pause between checks.

The simulated Vehicle Manager (``automationv3/plugins/vm/sim.py``) is a worked
example: its telemetry points read-only, the bench's inputs writable, fixed
values applied again every simulated frame.

The lifecycle of a job
----------------------

.. code-block:: text

   probe:  installed_version == job's?  ── no ──▶ released (try another job)
                │ yes
                ▼
           handle() bound ─▶ preconditions check/heal ── fail ──▶ released
                │ pass
                ▼
           steps run

   force:  install(version) if needed ─▶ start(version) ─▶ handle() bound
                ─▶ preconditions ── fail ──▶ blocked
                │ pass
                ▼
           steps run

UUTs stay as the last job left them; nothing is torn down between jobs.
That is what makes warm scheduling possible, and why preconditions should
check for the state a script needs rather than assume it.
