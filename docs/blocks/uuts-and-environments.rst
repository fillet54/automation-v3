UUTs and environments
=====================

.. rst-class:: lead

   A UUT plugin knows how to list, install and start a unit under test, and
   gives scripts a handle to it. An environment plugin describes where it
   runs.

The examples on this page come from the Apollo lunar module plugin,
``automationv3/plugins/apollo``: the ``lm`` UUT, and the ``sim`` and ``lms``
environments it runs in.

Environments
------------

Subclass :class:`~automationv3.framework.uut.Environment` and set ``name``:

.. code-block:: python

   class Sim(Environment):
       """The lunar module in software, stepped"""

       name = "sim"

       def __init__(self, workdir=None, **params):
           super().__init__(workdir=workdir, **params)
           self.workdir = Path(workdir or default_workdir())

       def fingerprint(self):
           return {
               "environment": self.name,
               "platform": platform.platform(),
               "python": platform.python_version(),
               "lm-model": MODEL_VERSION,
           }


   class Lms(Sim):
       """The Lunar Module Mission Simulator: real time, sped up by `pace`"""

       name = "lms"

       def __init__(self, workdir=None, pace=20, **params):
           super().__init__(workdir=workdir, pace=pace, **params)
           self.pace = float(pace)

       def fingerprint(self):
           return {**super().fingerprint(), "pace": self.pace, "terrain-model": TERRAIN_MODEL}

Scripts declare where they can run with ``(environments :sim :lms)``.

A worker creates one instance per environment it hosts, passing the
parameters from its config file:

.. code-block:: json

   {
     "environments": {
       "sim": {"workdir": "/var/lib/automation/sim"},
       "lms": {"workdir": "/var/lib/automation/lms", "pace": 20}
     }
   }

``fingerprint()``
   Facts about the environment that can affect results: tool versions, rig
   serial numbers, calibration dates, firmware of attached hardware. Return a
   JSON-serializable dict. The worker adds the framework's own version and
   commit. The fingerprint is hashed into every run's identity, and a rerun is
   refused if no live environment's fingerprint matches the original
   (:doc:`../operating/configuration-management`). Include everything that
   matters and nothing that changes on its own (no timestamps). ``lms``
   names its pace and its terrain model: both change what a flight does.

UUTs
----

Subclass :class:`~automationv3.framework.uut.UUT` and set ``name``:

.. code-block:: python

   class LunarModule(UUT):
       name = "lm"

       def list_versions(self):
           return [Version(id, digest(rope)) for id, rope in RELEASES.items()]

       def installed_version(self, env):
           ...

       def install(self, version, env):
           ...

       def start(self, version, env):
           ...

       def handle(self, version, env):
           return LunarModuleHandle(self, env)

Scripts declare what they test with ``(uut :lm)``.

``list_versions()``
   Every installable :class:`~automationv3.framework.uut.Version`, oldest
   first. The server calls it to offer versions when queuing; the newest is
   the default. A ``Version`` has an ``id`` (what people pick) and a
   ``digest`` that identifies the exact bits, e.g. a SHA-256 of the image.
   The lunar module's are its guidance computer's software: ``LUM099``,
   ``LUM131`` and ``LUM210``, each digested from its rope.

``installed_version(env)``
   The version installed in ``env`` now, or ``None``. Workers use it to
   decide whether a job can run warm.

``install(version, env)``
   Install a version. Called in force mode when the installed version differs
   from the job's; the worker then checks ``installed_version`` again and
   fails the job if the install didn't take.

``start(version, env)``
   Start the UUT fresh. Called in force mode, after install. The lunar module
   boots its default: a standard mission at powered descent initiation.

``handle(version, env)``
   The object scripts use to reach the UUT, bound to the UUT's name. Return
   ``None`` if scripts don't talk to it directly.

Versions and variations
-----------------------

A version is what ``install`` puts in the environment; everything else
about how a run sets the UUT up belongs to the script, as variations and
preconditions. The lunar module draws the line where Apollo did: the
Luminary rope (the software, woven into the computer's fixed memory) is the
version, and each mission's erasable load (its propellant, its approach,
its surface stay), the vehicle it flies, and where the flight starts are
chosen at boot. So a script that needs both missions has a variation for
each, with a precondition that boots the lunar module the variation's way:

.. code-block:: clojure

   (variations "mission"
     ["standard" [:standard]
      "extended" [:extended]])

   (Precondition "LM booted for the variation's mission, at PDI"
     (lm-ready? mission :pdi)
     :heal "Boot the variation's mission at PDI"
     (boot mission :pdi))

Runs of one variation can then reuse a booted lunar module, and every
version is tried against every mission. When a version can't take a
variation's setup (LUM099 has no extended missions), the heal fails and
the run is blocked rather than failed.

Handles
-------

A handle is any Python object. Scripts call its methods with the dot form, so
design it as the vocabulary scripts speak:

.. code-block:: clojure

   (.mission lm)                    ; -> :extended
   (.ready lm :standard :pdi)       ; -> true
   (.boot lm {:mission :extended})  ; -> :accepted, or :rejected-load

Guidelines for handles:

- Return edn-friendly values (keywords, numbers, strings, vectors), so
  scripts can compare them directly.
- Make actions return ``True``, so a call can be used directly as a step.
- Keep them small and well named. Wrap them in ``core.rst`` functions
  (``lm-ready?``, ``boot``) to give scripts a readable vocabulary, and put
  anything substantial into blocks (``StartLM``, ``FlyTo``).

Keeping time
------------

A run keeps time by one clock, the one its environment gives:
``Environment.clock(handles)``, called with the run's UUT handles (name to
handle) before the script starts. Wait's timeouts, its pauses between checks
and ``(Wait 2s)`` all go by it. Return ``None`` (the default) for the wall
clock, on real hardware, or a :class:`~automationv3.framework.clock.Clock`:

``WallClock()``
   Real time.

``SimClock(time_ref, step=None)``
   A simulation's time, read from a ref through the Read that accepts it.
   Sleeping waits, in real time, for the simulation to get that far; for a
   simulation that only moves when stepped, pass ``step(seconds)`` to run it
   forward instead.

The lunar module's two environments use one each. In ``sim``,
``SimClock`` reads ``lm.time.sim`` and steps the flight forward, so a
twelve-minute descent waits for nothing. In ``lms``, it has no step: the
flight runs on its own, twenty times faster than the wall clock, and every
look at the lunar module first catches the simulation up, so no process has
to run in the background.

The lifecycle of a job
----------------------

.. mermaid::
   :caption: The UUT plugin's methods, as a worker calls them for one job

   flowchart TB
     job([A claimed job]) --> mode{{Mode}}
     mode -- probe --> same{{"installed_version(env)<br/>is the job's?"}}
     same -- no --> released[Released: try another job]:::ghost
     same -- yes --> handle["handle(version, env)<br/>bound to the UUT's name"]
     mode -- force --> install["install(version, env)<br/>if it isn't installed"]
     install --> start["start(version, env)"]
     start --> handle
     handle --> pre{{"Preconditions<br/>hold, or heal?"}}
     pre -- yes --> steps[The steps run]:::success
     pre -- "no, probing" --> released
     pre -- "no, in force mode" --> blocked[blocked]:::warning

UUTs stay as the last job left them; nothing is torn down between jobs.
That is what makes warm scheduling possible, and why preconditions should
check for the state a script needs rather than assume it.

Local builds
------------

Builds live in a build repository of the plugin's own, for example a git
repository with its own clean-up. automation-v3 never stores them, and
``install`` pulls from that repository. A developer's machine can add to it:
the local client finds a build they've just made and offers to upload it
(see :doc:`../operating/local-client`). Two optional methods make that work:

.. code-block:: python

   class LunarModule(UUT):
       name = "lm"

       def find_local_build(self, path):
           """The newest build in `path`, where builds land on this machine"""
           build = Path(path) / "luminary.json"
           if not build.is_file():
               return None
           found = digest(parse(build.read_text()))
           return LocalBuild(self.name, build, f"local-{found[:12]}", found,
                             build.stat().st_mtime)

       def upload_build(self, build):
           """Put it in the build repository; return its Version"""
           repo = Path(os.environ["AUTOMATION_LM_BUILDS"])
           (repo / build.id).mkdir(parents=True, exist_ok=True)
           shutil.copy2(build.path, repo / build.id / "luminary.json")
           return Version(build.id, build.digest)

``find_local_build(path)``
   ``path`` is the folder the developer's ``client.json`` names for this UUT.
   Return a :class:`~automationv3.framework.uut.LocalBuild` for the newest
   build there: its ``digest`` must be computed the same way as the
   ``digest`` of the versions ``list_versions`` returns, because the client
   compares them to tell whether the build is uploaded already. ``id`` is the
   version id it gets once uploaded.

``upload_build(build)``
   Called on the developer's machine, with their own credentials, only for a
   build no listed version has the digest of. Put it where ``list_versions``
   and ``install`` will find it, on the server and on workers, and return its
   :class:`~automationv3.framework.uut.Version`.

``report_versions()``
   The versions a report may run on. The default is everything
   ``list_versions`` returns. A plugin whose ``list_versions`` includes
   uploaded builds leaves them out here, because uploaded builds are for
   scratch runs only. Report pages offer and accept only these, while
   scratch runs may use any listed version.

None of these is required. A UUT without them simply has no local builds to
offer. The lunar module implements all three, against the folder named by
``AUTOMATION_LM_BUILDS``; ``automation-v3 demo`` sets it up, with a build of
LUM131 with its defect fixed waiting in ``demo/local-build``.
