Command line
============

.. rst-class:: lead

   ``automation-v3`` runs the server, a worker, or scripts on this machine.

.. code-block:: text

   Automation Framework

   Usage:
       automation-v3 demo [--path PATH] [--port PORT] [--no-docs]
       automation-v3 server [--port PORT] [--dbpath PATH]
                            [--workspace-path PATH] [--reports-path PATH]
                            [--docs-path PATH] [--local-worker] [--config PATH]
                            [--debug]
       automation-v3 worker [--port PORT] [--config PATH]
                            [--central-server URL] [--no-http] [--debug]
       automation-v3 run SCRIPT... [--root PATH] [--config PATH]
                         [--env NAME]... [--variation NAME]... [--filter EXPR]
                         [--uut NAME=VERSION]... [--reports-path PATH]
       automation-v3 (-h | --help)

   Commands:
       demo                   set up a demo (sample scripts, requirements and
                              these docs) in a fresh folder, and serve it with
                              a worker. Deletes an earlier demo at --path
       server                 serve the web app and the job API, optionally
                              with a worker in the same process
       worker                 take jobs from a server and run them
       run                    run scripts on this machine, without a server

   Options:
       -h --help              show this help message and exit
       --port=PORT            tcp port to bind to [default: 8080]
       --dbpath=PATH          path to application database file
                              [default: ./automationv3.db]
       --workspace-path=PATH  path to git repo [default: ./]
       --reports-path=PATH    directory holding reports and runs
                              [default: ./reports]
       --docs-path=PATH       built HTML documentation to serve at /docs
       --path=PATH            the demo's folder [default: ./demo]
       --no-docs              don't build the documentation
       --central-server=URL   host:port of the central server
       --config=PATH          worker config (JSON) naming the environments
                              it hosts
       --no-http              run the worker without its status page
       --local-worker         also run a worker inside the server process
                              (hosting the environments in --config)
       --root=PATH            root script path SCRIPTs are relative to
                              [default: ./]
       --env=NAME             environment to run in (default: all hosted)
       --variation=NAME       variation to run (default: all)
       --filter=EXPR          EDN predicate selecting variations
       --uut=NAME=VERSION     UUT version to use (default: newest)
       --debug                enables autoload [default: false]

``demo``
--------

Sets up a fresh demo folder (sample scripts, requirements and these docs)
and serves it with a worker in-process. See :doc:`../overview/getting-started`.

``server``
----------

Serves the web app and the job API. ``--workspace-path`` is the git checkout
scripts are read from; ``--reports-path`` is where finished runs are stored.
With ``--local-worker`` it also runs a worker in-process, hosting the
environments in ``--config``. ``--docs-path`` serves a build of these docs
at ``/docs``, with a **Docs** link in the navigation.

``worker``
----------

Takes jobs from the server at ``--central-server`` and runs them in the
environments named in ``--config``. See :doc:`../operating/workers`.

``run``
-------

Runs scripts on this machine with no server or database. ``SCRIPT`` paths
are relative to ``--root``. It prints each step, writes a normal report
folder under ``--reports-path`` and exits non-zero unless every run passed.

.. code-block:: bash

   automation-v3 run BRA/tc_bra_00004.rst --root test/data/rvts --config test/data/worker.json --variation limp-home --uut demo=1.0.0
