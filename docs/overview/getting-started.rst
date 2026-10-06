Getting started
===============

.. rst-class:: lead

   Run the sample test set on one machine: a server, a worker, the simulated
   ``demo`` UUT and a dozen example scripts.

The demo
--------

From a clone of the repository, with Python 3.10 or newer:

.. code-block:: bash

   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[docs]"
   automation-v3 demo

Open http://localhost:8080.

``demo`` builds a fresh ``./demo`` folder and serves it with a worker in the
same process. It holds a workspace (a git repository of the sample scripts,
with three more branches), the sample requirements, the ``sim`` and ``bench``
environments' work directories, and these docs, linked as **Docs** in the
app's navigation. Running it again deletes the earlier demo and starts over;
it never deletes a folder it didn't make.

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

The install must be editable: the demo reads the sample scripts and these
docs' sources from the checkout.

Setting it up by hand
---------------------

To run against the sample set without the demo, load the sample data and
start a server and a worker:

.. code-block:: bash

   python test/data/load_sample.py
   python test/data/make_workspaces.py
   automation-v3 server --workspace-path ./test/data/git_repos/master

In a second terminal:

.. code-block:: bash

   automation-v3 worker --port 8081 --central-server localhost:8080 --config test/data/worker.json

Or run everything in one process, with a worker inside the server:

.. code-block:: bash

   automation-v3 server --workspace-path ./test/data/git_repos/master --local-worker --config test/data/worker.json

Add ``--docs-path docs/_build/html`` to serve a build of these docs at
``/docs``.

A first tour
------------

1. **Workspace** shows the script tree. Open ``BRA/tc_bra_00004.rst``: the
   variation selector under the breadcrumbs switches the page between the
   ``normal``, ``limp-home`` and ``emergency`` variations, and **Details**
   lists where it runs, what it tests and its variations.
2. Press **Queue…** to run it. Leave the defaults and queue: a report is
   created for it.
3. **Reports** lists the report. Open a run to see each step with its badge,
   its duration and anything it printed.
4. **Requirements** lists requirements with their linked scripts. Pick a few
   and add them to a report to see the rollup.

``test/data/rvts/README.rst`` lists what each example script shows; several
fail, block or refuse to queue on purpose.

Running without a server
------------------------

``automation-v3 run`` runs scripts on this machine with no server or database,
using the same worker config. It prints each step, writes a normal report
folder and exits non-zero unless every run passed:

.. code-block:: bash

   automation-v3 run BRA/tc_bra_00004.rst --root test/data/rvts --config test/data/worker.json --variation limp-home --uut demo=1.0.0

Building these docs
-------------------

.. code-block:: bash

   cd docs
   make html

The site is written to ``docs/_build/html``.
