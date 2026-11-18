Attaching files
===============

.. rst-class:: lead

   A block can attach files to the run: logs, captures, snapshots of the UUT's
   state. They are stored with the run and listed under the step.

.. code-block:: python

   from automationv3.framework.steps import attach

   class AttachTrajectory(BuildingBlock):
       """Attach the flight so far to the run: <label>.csv and <label>.svg::

           (AttachTrajectory "descent")
       """

       def execute(self, label):
           rows = context.lookup("lm").trajectory_rows()
           attach(f"{label}.csv", as_csv(rows))
           attach(f"{label}.svg", trajectory_svg(rows, title=label))
           return BlockResult(True, stdout=f"attached {label}.csv and {label}.svg")

This is the lunar module's own block (``plugins/apollo/blocks.py``): each
landing in the Apollo example attaches its descent as a table and a plot.

``attach(name, data)`` takes ``bytes`` or text (encoded as UTF-8). It can only
be called while a script is running.

Where files go
--------------

A worker uploads each file to the server as it is attached, and the server
stores it in the run's ``files/`` folder. If a step attaches the same name
twice, the second is numbered rather than overwriting the first. The run page
lists each file under the step that attached it, with a link to download it.

``automation-v3 run`` stores them the same way, in its local report folder.

Guidelines
----------

- Name files for what they show, with an extension that says their type
  (``after-braking.json``, ``can-trace.blf``).
- Mention the attachment in ``stdout`` so the step's output points to it.
- Attach evidence, not noise: anything attached is kept with the run for as
  long as the report is.
