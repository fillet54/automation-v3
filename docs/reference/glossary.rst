Glossary
========

.. glossary::
   :sorted:

   BuildingBlock
      A step scripts call by name, written in Python. See :doc:`../blocks/writing-blocks`.

   closure
      A script plus every ``core.rst`` and import it loaded. Stored with each run.

   combination
      One (script, environment, variation) a report expects a run of.

   core.rst
      A folder's shared definitions and declarations, loaded by every script below it.

   defblock
      A composite block defined in script code; reports as one step with nested calls.

   drift
      An environment whose fingerprint no longer matches a run being rerun.

   environment
      Where a script runs, such as a simulator or a bench. Hosted by workers.

   fingerprint
      Facts about an environment, and the framework, that can affect results.

   force mode
      Running a job with its UUTs installed and started fresh.

   handle
      The object bound to a UUT's name that scripts call methods on.

   heal
      The part of a precondition that establishes the state it checks.

   identity
      The hash of a run's closure, variation values, UUT versions and fingerprint.

   precondition
      The state a script needs before its steps run, with an optional heal.

   probe
      Trying a job against the environment as it is, without reinstalling.

   report
      A named, growing collection of runs rolled up to requirements.

   rollup
      Each tracked requirement's state in a report: green, red or partial.

   rvt
      The rst directive holding script code.

   scratch space
      Where scripts under development run, outside any report.

   UUT
      A unit under test, installed into and started in an environment.

   variation
      One way of running a script, binding its variation symbols to values.

   worker
      A process next to the hardware that pulls and runs jobs.
