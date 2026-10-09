Planning a test before writing it
=================================

.. rst-class:: lead

   Write a test's flow first, as titled groups of steps described in words,
   so it can be reviewed as a whole. Then replace the words with real steps,
   one group at a time.

Placeholder steps
-----------------

``(TBD "what the step will do")`` is a step that isn't written yet. Put them
in titled ``rvt`` blocks, one block per stage of the test:

.. code-block:: rst

   .. rvt:: Engage the autopilot

      (TBD "Set the autopilot engage switch to ON")
      (TBD "Verify the autopilot reports engaged within 1 frame")

   .. rvt:: Roll hold is the default lateral mode

      (TBD "Verify heading hold is not active")
      (TBD "Verify the active lateral mode is roll hold")

The script page shows each ``TBD`` as a step *to be written*, and opens the
titled blocks that hold them, so the page reads as the test's procedure:
reviewers see the stages and what each will do, with the requirements and
variations around them.

Everything else works as usual around them. A ``TBD`` can sit in a ``defn``
in a ``core.rst`` (a shared step nobody has written yet), in a precondition's
check or heal, or among real steps. Where a value is expected, a ``TBD`` comes
out true, so the flow after it runs too.

Running a test that isn't finished
----------------------------------

A script with ``TBD`` steps can be queued and run, for example in the
:doc:`scratch space <../operating/scratch>`. The real steps run; each ``TBD``
is reported as :status:`to do` and the run goes on. A run that reached any
``TBD`` can't pass: if nothing else stopped it, its outcome is
**incomplete**, and the requirements it covers roll up partial, never green.

The static check counts them, as a warning on the script page: *10 steps
are still to be written (TBD)*.

Check what you can now
----------------------

Even before the system under test can be driven, a test's own data can be
checked. The Vehicle Manager examples in the sample set state the expected
result of each variation in a table, and their first step checks that table
against the requirement, written once as a function in the folder's
``core.rst``:

.. code-block:: clojure

   (Verify (transition-allowed? from to) = allowed)

That step is real from the start: a mistake in the table fails the run long
before anyone flies it.

Examples
--------

The ``VM`` folder of the sample set holds tests written this way, for the
Vehicle Manager of a satellite platform: 66 scripts across ten subsystems
(executive, telecommand, telemetry, modes, FDIR, attitude control, power,
thermal, time and storage), testing the 64 requirements of
``test/data/requirements/vehicle_manager.rst``. The mode, power and
telecommand tests have since been written in full, against a simulated
Vehicle Manager; the others are still flows and come out incomplete. Compare
the two kinds side by side: the flow below, and ``VM/EPS/tc_eps_002.rst``
written out.

.. literalinclude:: ../../test/data/rvts/VM/FDIR/tc_fdir_003.rst
   :language: rst
