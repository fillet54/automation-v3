Command line
============

.. rst-class:: lead

   ``automation-v3`` runs the server, a worker, the local client, or scripts
   on this machine.

.. code-block:: text

   Automation Framework

   Usage:
       automation-v3 demo [--path PATH] [--port PORT] [--no-docs] [--debug]
       automation-v3 server [--port PORT] [--dbpath PATH]
                            [--workspace-path PATH] [--reports-path PATH]
                            [--docs-path PATH] [--local-worker] [--config PATH]
                            [--settings PATH] [--debug]
       automation-v3 worker [--port PORT] [--config PATH]
                            [--central-server URL] [--no-http] [--debug]
       automation-v3 run SCRIPT... [--root PATH] [--config PATH]
                         [--env NAME]... [--variation NAME]... [--filter EXPR]
                         [--uut NAME=VERSION]... [--reports-path PATH]
       automation-v3 client [--port PORT] [--workspace-path PATH] [--server URL]
                            [--config PATH] [--data-path PATH] [--debug]
       automation-v3 login --server URL [--email EMAIL]
       automation-v3 logout [--server URL]
       automation-v3 whoami [--server URL]
       automation-v3 builds [--server URL]
       automation-v3 scratch SCRIPT... [--root PATH] [--server URL]
                             [--env NAME]... [--variation NAME]...
                             [--uut NAME=VERSION]...
                             [--no-wait]
       automation-v3 report edit REPORT [--title TEXT] [--number TEXT]
                            [--revision TEXT] [--author TEXT]
                            [--sign ROLE=NAME]... [--applicable DOC]...
                            [--reference DOC]...
       automation-v3 report export REPORT [--out DIR] [--template DIR]
       automation-v3 report reopen REPORT
       automation-v3 requirements import SOURCE... [--spec KEY] [--baseline NAME]
                            [--title TEXT] [--level LEVEL] [--parents KEYS]
                            [--sheet NAME] [--dbpath PATH] [--server URL]
       automation-v3 requirements log [--limit N] [--dbpath PATH]
       automation-v3 requirements history ID [--dbpath PATH]
       automation-v3 requirements diff FROM TO [--spec KEY]
                            [--subsystem NAME] [--dbpath PATH]
       automation-v3 lsp [--scripts PATH] [--dbpath PATH]
       automation-v3 (-h | --help)

   Commands:
       demo                   set up a demo (the Apollo lunar module example's
                              scripts and requirements, and these docs) in a
                              fresh folder, and serve it with a worker.
                              Deletes an earlier demo at --path
       server                 serve the web app and the job API, optionally
                              with a worker in the same process
       worker                 take jobs from a server and run them
       run                    run scripts on this machine, without a server
       client                 the local client's web UI, on this machine only:
                              your worktrees' scripts, checked as you write them,
                              run in scratch on the central server (or here,
                              with --config). Sign in first with login
       login                  sign this machine in to a central server: it
                              emails you a link to approve it
       logout                 sign this machine out, and revoke its token
       whoami                 who this machine is signed in as
       scratch                run scripts from your worktree in the central
                              server's scratch space, on its workers: in-work
                              edits included. Waits and prints each step.
                              With --uut NAME=local it uses your local build
                              of NAME, uploading it first if it isn't yet
       builds                 your local builds (see client.json), and whether
                              each is uploaded
       report edit            set a report's document fields: its title,
                              number, revision and author, who signs it, and
                              its applicable and reference documents
       report export          freeze a report and write its PDF and bundle,
                              report-<id>.zip
       report reopen          unfreeze an exported report, so runs can be
                              added to it again
       requirements import    import requirements, in order: DOORS export
                              folders (or zips of them), or a spec as a
                              spreadsheet (CSV, TSV or Excel) or a list, one
                              per line (with --spec). Into the
                              database, or with --server into a central
                              server (admins only)
       requirements log       the latest imports, and what each changed
       requirements history   every change to a requirement, and the
                              baselines it is in
       requirements diff      the requirements added, removed and changed
                              from one context to another: trunk, trunk@N
                              (as of import N), set:NAME (a baseline set)
                              or SPEC@BASELINE
       lsp                    the language server for scripts, on stdin and
                              stdout: errors as you type, completion, hover
                              and signature help, in any editor that speaks
                              the Language Server Protocol. Requirement ids
                              are read from the database, if it is there

   Options:
       -h --help              show this help message and exit
       --port=PORT            tcp port to bind to [default: 8080]
       --dbpath=PATH          path to application database file
                              [default: ./automationv3.db]
       --workspace-path=PATH  the scripts folder, in a git worktree: its top or
                              a folder below it; the same folder in each
                              other worktree is that branch's [default: ./]
                              (not used when the settings name a [git]
                              remote to mirror)
       --reports-path=PATH    directory holding reports and runs
                              [default: ./reports]
       --docs-path=PATH       built HTML documentation to serve at /docs
       --path=PATH            the demo's folder [default: ./demo]
       --no-docs              don't build the documentation
       --central-server=URL   the central server: host:port, or a URL
       --config=PATH          worker config (JSON) naming the environments
                              it hosts
       --settings=PATH        server settings (TOML): sign-in, mail and a git
                              remote to mirror. Without it the server is
                              single-user
       --no-http              run the worker without its status page
       --local-worker         also run a worker inside the server process
                              (hosting the environments in --config)
       --root=PATH            root script path SCRIPTs are relative to
                              [default: ./]
       --server=URL           a central server (default: the one you last
                              signed in to)
       --email=EMAIL          your work email (asked for if not given)
       --no-wait              queue and print the runs' links, without waiting
       --data-path=PATH       where the client keeps its own scratch runs
                              (default: ~/.local/share/automation-v3/client)
       --env=NAME             environment to run in (default: all hosted)
       --variation=NAME       variation to run (default: all)
       --filter=EXPR          EDN predicate selecting variations
       --uut=NAME=VERSION     UUT version to use (default: newest)
       --debug                Flask's development server, with its debugger
                              and reloading on code changes, on 127.0.0.1
                              only [default: false]
       REPORT                 a report's folder (in the reports path)
       --title=TEXT           the report's name, its document's title; or a
                              CSV or list spec's title
       --number=TEXT          the document's number
       --revision=TEXT        the document's revision
       --author=TEXT          the document's author
       --sign=ROLE=NAME       who signs for a role, e.g. "Approved by=J. Doe"
       --applicable=DOC       an applicable document, "NUMBER | REVISION | TITLE";
                              replaces the report's list
       --reference=DOC        a reference document, "NUMBER | REVISION | TITLE";
                              replaces the report's list
       --out=DIR              where to write the bundle (default: the report
                              folder's exports/)
       --template=DIR         the document template (default: the built-in one)
       SOURCE                 an export folder (holding manifest.json) or a
                              zip of one; or a spec's requirements in a .csv,
                              .tsv, .xlsx or .txt (a list), with --spec
       --sheet=NAME           the sheet of an Excel workbook (default: the
                              first)
       --baseline=NAME        the baseline a CSV or list is (default: trunk)
       --level=LEVEL          a CSV or list spec's level: system, segment or
                              software [default: software]
       --parents=KEYS         the specs a CSV or list spec's requirements
                              trace up to, comma separated
       --limit=N              how many imports to show [default: 10]
       --spec=KEY             the spec a CSV or list is; for diff, only
                              this spec's requirements
       --subsystem=NAME       only this subsystem's requirements
       --scripts=PATH         the folder scripts are in (default: the folder
                              the editor has open)

``demo``
--------

Sets up a fresh demo folder (the Apollo lunar module example's scripts and
requirements, and these docs) and serves it with a worker in-process. See :doc:`../overview/getting-started`.

``server``
----------

Serves the web app and the job API. ``--workspace-path`` is the scripts
folder in a git checkout (its top or a folder below it); the same folder in
each of the repository's worktrees is that branch's workspace. ``--reports-path`` is where finished runs are stored.
``--settings`` makes it a central server: sign-in, mail, and a mirror of the
team's git remote instead of ``--workspace-path`` (see
:doc:`../operating/deployment`).
With ``--local-worker`` it also runs a worker in-process, hosting the
environments in ``--config``. ``--docs-path`` serves a build of these docs
at ``/docs``, with a **Docs** link in the navigation.

``worker``
----------

Takes jobs from the server at ``--central-server`` and runs them in the
environments named in ``--config``. A central server needs a worker token,
``"token"`` in the config or ``AUTOMATION_WORKER_TOKEN``. See
:doc:`../operating/workers`.

``client``, ``login``, ``logout``, ``whoami``, ``scratch`` and ``builds``
-------------------------------------------------------------------------

The local client, on your own machine (see :doc:`../operating/local-client`).
``login --server URL`` signs this machine in by emailed link, and the rest use
that sign-in. ``client`` serves the web UI for your worktrees on
``127.0.0.1``. ``scratch SCRIPT...`` uploads scripts from your worktree, edits
included, to run in the central server's scratch space, printing each step.
``builds`` lists your local builds and whether each is uploaded.

.. code-block:: bash

   automation-v3 login --server https://automation.example.com
   automation-v3 client --workspace-path ~/work/scripts/rvts
   automation-v3 scratch ALM/tc_alm_003.rst --env sim --uut lm=local

``run``
-------

Runs scripts on this machine with no server or database. ``SCRIPT`` paths
are relative to ``--root``. It prints each step, writes a normal report
folder under ``--reports-path`` and exits non-zero unless every run passed.

.. code-block:: bash

   automation-v3 run ALM/tc_alm_003.rst --root automationv3/examples/apollo/rvts --config demo/worker.json --env sim --variation extended --uut lm=LUM131

``requirements``
----------------

Imports and inspects requirements. ``import`` reads each ``SOURCE`` and
imports them in the order given, saying what happened to each spec; a source
with a problem is refused whole and changes nothing. A source is an export
folder (see :doc:`requirements-export`) or a zip of one, or one spec's
requirements as a CSV or a list (see :ref:`flat-requirements`), which needs
``--spec`` to say which spec it is, and may take ``--title``, ``--baseline``,
``--level`` and ``--parents`` (and ``--sheet``, for a workbook). ``log`` lists the latest imports and the requirements each
added, removed or changed; ``history`` follows one requirement through every
import and baseline.

With ``--server URL``, ``import`` uploads each source to a central server
instead, which takes imports from admins only.

``diff`` compares two contexts: ``trunk``, ``trunk@N`` (trunk as of import
``N``), ``set:NAME`` (a baseline set) or ``SPEC@BASELINE``. Each line is a
requirement and what changed: ``added``, ``removed``, or its ``text``,
``metadata``, ``links`` or ``section``.

.. code-block:: bash

   automation-v3 requirements import exports/2026-10-15
   automation-v3 requirements import srs.csv --spec SRS --parents LM
   automation-v3 requirements diff "set:Release 1" "set:Release 2" --spec LGC
   automation-v3 requirements history LGC-GDN-004

``lsp``
-------

Runs the language server for scripts on stdin and stdout, which is how
editors start one. It reports the same errors and warnings a script's page
shows, as you type, and completes the names a block can use: blocks,
builtins, the definitions of the script and its ``core.rst`` files, UUT
handles and variation values. Hovering a name says what it is, and typing a
call shows how it is called. In prose, ``:req:`` ids complete, show the
requirement's text on hover, and are flagged when they aren't requirements:
these come from the database at ``--dbpath``, when there is one. The web
app's editor uses the same server.

The scripts root is the folder the editor has open; ``--scripts`` names
another. See
:doc:`../operating/editor` for setting up an editor.
