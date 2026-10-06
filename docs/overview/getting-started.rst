Getting started
===============

.. rst-class:: lead

   Run the sample test set on one machine: a server, a worker, the simulated
   ``demo`` UUT and a dozen example scripts.

Install
-------

Automation v3 needs Python 3.10 or newer.

.. code-block:: bash

   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   pip install -e .

Load the sample data
--------------------

The sample database holds the requirements the example scripts reference, and
the sample workspace is a git repository of those scripts (from
``test/data/rvts``):

.. code-block:: bash

   python test/data/load_sample.py
   python test/data/make_workspaces.py

Start the server and a worker
-----------------------------

.. code-block:: bash

   automation-v3 server --workspace-path ./test/data/git_repos/master

In a second terminal, start a worker. Its config names the environments it
hosts; the sample one hosts ``sim`` and ``bench``:

.. code-block:: bash

   automation-v3 worker --port 8081 --central-server localhost:8080 --config test/data/worker.json

Or run everything in one process, with a worker inside the server:

.. code-block:: bash

   automation-v3 server --workspace-path ./test/data/git_repos/master --local-worker --config test/data/worker.json

Open http://localhost:8080.

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
