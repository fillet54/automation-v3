Getting started
===============

.. rst-class:: lead

   Run the example test set on one machine: a server, a worker, the
   simulated Apollo lunar module and its example scripts.

The demo
--------

From a clone of the repository, with Python 3.11 or newer:

.. code-block:: bash

   python -m venv .venv
   source .venv/bin/activate
   pip install -e .
   automation-v3 demo

Open http://localhost:8080.

``demo`` builds a fresh ``./demo`` folder and serves it with a worker in the
same process. It holds a workspace (a git repository of the example scripts,
with three more branches), the example's requirements and their DOORS
history, the ``sim`` and ``lms`` environments' work directories, the lunar
module's build repository with a local build ready to upload, and these
docs, linked as **Docs** in the app's navigation. Running it again deletes
the earlier demo and starts over; it never deletes a folder it didn't make.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Option
     - Meaning
   * - ``--path PATH``
     - the demo's folder (default ``./demo``)
   * - ``--port PORT``
     - the port to serve on (default 8080)
   * - ``--no-docs``
     - don't build the documentation

The example ships with the package (``automationv3/examples/apollo``), so
the demo works from any install. The documentation is built only from a
source checkout, which has ``docs/``.

The example
-----------

The unit under test is the Apollo lunar module's powered descent: a small
simulation of the vehicle and its guidance computer, the ``lm`` UUT. Scripts
key its display and keyboard (the DSKY), flip its panel switches, inject
faults from the simulator's bench, run its time forward and check what the
vehicle and the computer did.

- Its **versions** are the guidance computer's software, three Luminary
  ropes. ``LUM099`` has no extended missions, so scripts that need one are
  blocked; ``LUM131`` has a defect invented for the example, which one check
  catches on extended missions; ``LUM210`` fixes it, and is the default.
- Its **variations** are how it is booted: the mission (standard, or
  extended, with more propellant, batteries, oxygen and water) and where the
  flight starts (powered descent initiation, high gate, low gate or the
  surface). Runs of the same variation reuse a booted lunar module.
- Its **environments** are ``sim``, stepped as fast as the computer can
  go, and ``lms``, the mission simulator, which runs in real time sped up
  twenty times.

Setting it up by hand
---------------------

Once a demo folder exists, a server and a separate worker can run on it:

.. code-block:: bash

   automation-v3 server --workspace-path demo/workspace/master --dbpath demo/automationv3.db

In a second terminal:

.. code-block:: bash

   automation-v3 worker --port 8081 --central-server localhost:8080 --config demo/worker.json

Or run everything in one process, with a worker inside the server:

.. code-block:: bash

   automation-v3 server --workspace-path demo/workspace/master --dbpath demo/automationv3.db --local-worker --config demo/worker.json

Add ``--docs-path docs/_build/html`` to serve a build of these docs at
``/docs``.

A first tour
------------

1. **Workspace** shows the script tree. Open ``LND/tc_lnd_001.rst``: the
   variation selector under the breadcrumbs switches the page between the
   four mission and start point variations, and **Details** lists where it
   runs, what it tests and its variations.
2. Press **Queue…** to run it. Leave the defaults and queue: a report is
   created for it. Each run attaches the flight's trajectory, as a table
   and as a plot.
3. **Reports** lists the report. Open a run to see each step with its badge,
   its duration and anything it printed.
4. **Requirements** lists requirements with their linked scripts. Pick
   ``set:Release 2``, queue its requirements on ``LUM131`` and see the
   rollup turn red where the defect is; queue them again on ``LUM210``.

``automationv3/examples/apollo/rvts/README.rst`` lists what each example
script shows; several fail, block or refuse to queue on purpose.

Running without a server
------------------------

``automation-v3 run`` runs scripts on this machine with no server or database,
using the same worker config. It prints each step, writes a normal report
folder and exits non-zero unless every run passed:

.. code-block:: bash

   automation-v3 run ALM/tc_alm_003.rst --root automationv3/examples/apollo/rvts --config demo/worker.json --env sim --variation extended --uut lm=LUM131

That one fails on purpose: LUM131's defect.

Building these docs
-------------------

.. code-block:: bash

   cd docs
   make html

The site is written to ``docs/_build/html``.
