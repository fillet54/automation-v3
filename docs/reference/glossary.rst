Glossary
========

.. glossary::
   :sorted:

   BuildingBlock
      A step scripts call by name, written in Python. See :doc:`../blocks/writing-blocks`.

   closure
      A script plus every ``core.rst`` and import it loaded. Stored with each run.

   connector
      A point of a UUT scripts read, wait on and drive, named by its path.
      See :doc:`../scripts/connectors`.

   connector group
      Connectors tested together, such as redundant units: Verify and Wait
      check every member. See :doc:`../scripts/connectors`.

   combination
      One (script, environment, variation) a report expects a run of.

   core.rst
      A folder's shared definitions and declarations, loaded by every script below it.

   action
      A block that does something to the system. Fails if it can't.

   assertion
      A block that checks something. Fails when the check comes out false.

   value block
      A block that reads something and gives it back. Reported quietly, with its value.

   cleanup
      What a block registers to run when the script ends, however it ends,
      such as SetFixedValue releasing its value.

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
