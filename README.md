
# Automation-v3

## Try the demo

From a clone of this repository:

```
python -m venv .venv
source .venv/bin/activate
pip install -e ".[docs]"
automation-v3 demo
```

Then open http://localhost:8080.

`demo` sets up everything in a fresh `./demo` folder and serves it, with a
worker in the same process:

- a workspace: a git repository of the sample scripts (`test/data/rvts`)
  on `master`, with three more branches as worktrees;
- the sample requirements, loaded into the demo's database;
- the `sim` and `bench` environments, working under `demo/environments`;
- this project's documentation, built and linked as **Docs** in the
  app's navigation.

Each run deletes the earlier demo and starts again; it won't delete a
folder it didn't make. Use `--path` for another folder, `--port` for
another port, and `--no-docs` to skip building the documentation. The
install must be editable (`-e`): the demo reads the sample scripts and
documentation sources from the checkout. Without the `[docs]` extra the
demo runs without documentation.

## Running it yourself

1. Install as above, then make the sample database and workspace:
```
python test/data/load_sample.py
python test/data/make_workspaces.py
```
2. Run!
```
automation-v3 server --workspace-path ./test/data/git_repos/master
```
3. Start a worker (in another terminal) to execute queued scripts. The
   config names the environments it hosts; this one hosts the sample `sim`
   and `bench`.
```
automation-v3 worker --port 8081 --central-server localhost:8080 --config test/data/worker.json
```
Pick requirements on the **Requirements** page (or open a script and press
**Queue…**), choose environments, UUT versions and variations, and queue.
The report rolls each requirement up as Green (every linked script passed
in every environment and variation), Red (any failed) or Partial.

Add `--no-http` to run a worker without its status page.

To run everything in one process instead, start the server with its own
worker; it takes jobs straight from the server's database. Separate workers
can still connect as well:
```
automation-v3 server --workspace-path ./test/data/git_repos/master --local-worker --config test/data/worker.json
```

To serve the documentation at `/docs` (with a **Docs** link in the
navigation), build it and pass `--docs-path`:
```
make -C docs html
automation-v3 server --workspace-path ./test/data/git_repos/master --docs-path docs/_build/html
```

### Running scripts without a server

`run` runs scripts on this machine, with no server or database, using the
same worker config. It prints each step, writes a normal report folder and
exits non-zero unless every run passed:

```
automation-v3 run BRA/tc_bra_00004.rst --root test/data/rvts --config test/data/worker.json
automation-v3 run BRA/tc_bra_00004.rst --root test/data/rvts --config test/data/worker.json --variation limp-home --uut demo=1.0.0
```

## Code organization

Each layer only imports from the ones above it (`test/test_layers.py`
checks this):

| Package | Holds | Must not use |
| --- | --- | --- |
| `automationv3/framework` | The script language and its execution: edn, lisp, closures, preconditions, variations, planning, UUT/environment interfaces | storage, HTTP, Flask |
| `automationv3/services` | Concepts that need storage or processes: workspaces, requirements, reports, the job queue, workers | Flask, the web layer |
| `automationv3/web` | Flask pages and the HTTP job API, templates and static files | |
| `automationv3/cli.py` | `server`, `worker` and `run` | |
| `automationv3/plugins` | BuildingBlocks, UUTs and environments | services, web |

A worker takes jobs from anything with the small server interface in
`services/worker/worker.py`: the HTTP client (`services/worker/client.py`)
or `LocalServer` (`services/worker/local.py`), which `run` uses in-process.

## Scripts

Scripts are authored in git; the workspace is a read-only viewer. A script
is a reStructuredText (`.rst`) document whose code lives in `rvt`
directives; each form in an `rvt` block is a step, and the prose between
them is the script's documentation:

```rst
================
Brake Monitoring
================
Checks the brake pressure stays under the limit.

Requirements
------------
1. :req:`VMCBRA00001`

.. rvt::
   :definitions:

   (def target 60)

Steps
-----

.. rvt::

   (set-reading :brake-pressure target)
   (Verify (reading :brake-pressure) <= max-pressure)
```

Any `.rst` with an `rvt` block is a script (plain documents like a
README are only documentation). Each
folder (including the root) may hold a `core.rst` of shared definitions
(`def`, `defn`, `defblock`). A script loads the `core.rst` of every folder from the
root down to its own, then those of folders it imports with
`(import FOLDER)`. Inner definitions shadow outer ones; imports only add
definitions and never override a name the script's own chain defines. A step whose head is
a `defn` is called with evaluated arguments and passes if it returns
something truthy; every other step runs through its BuildingBlock, whose
`execute` also gets evaluated arguments (a block that wants the forms as
written implements `execute_forms` instead).

Scripts reference requirements with ``:req:`ID` `` in their documentation.
A script may declare variations, each binding the same symbols to
different values for its own run:

```clojure
(variations "mode pressure"
  ["nominal"  [:normal 60]
   "degraded" [:limp-home 75]])
```

The queue dialog can untick variations or filter them with an EDN
predicate over those symbols plus `name` and `index`, e.g.
`(not= mode :degraded)`.

Preconditions state what must hold before the steps run, and may heal it:

```clojure
(Precondition "Demo running in normal mode"
  (demo-in-mode? :normal)
  :heal (start-demo :normal))
```

Workers run the job whose preconditions already hold (or heal) first,
leaving UUTs as they are between jobs. Only when no queued job is ready do
they start the UUTs fresh for the oldest one; a precondition that still
fails then makes the run **blocked**. Scripts reach a UUT through a handle
bound to its name, e.g. `(.mode demo)`.

`test/data/rvts` is an example set that tests every BRA and FUE
requirement; its `README.rst` lists what each script shows and which ones
fail on purpose.

A script can define things too. Definitions are never reported as steps;
a script's definitions section (an `rvt` block with the `:definitions:`
option, placed before any step) loads with the closure, and pages show it
collapsed:

```rst
.. rvt::
   :definitions:

   (def stop-pressure 70)
```

Blocks compose in scripts. Called at the top level or in a plain `defn`, a
block acts as its own step: it is reported, and a failure stops the script.
A `defblock` (in a `core.rst`) reports as one step with its calls nested
beneath it, and passes on what it returns. `(passes? (Block ...))` checks a
block without failing, and `(quietly ...)` leaves calls out of the output:

```clojure
(defblock brakes-hold [pressure]
  (StartDemo {:mode :normal :readings {:brake-pressure pressure}})
  (Verify (reading :brake-pressure) <= max-pressure))
```

Steps render through their BuildingBlock: a block can override `as_html`
(or `as_rst`) to show its arguments readably, e.g. a configuration as a
table; otherwise the step shows as code.

`(environments :sim ...)` and `(uut :demo ...)` declare where a script can
run and what it tests. They are inherited from the `core.rst` chain and the
script can override them. UUTs and environments are plugins in
`automationv3/plugins` (see `plugins/sample`).


## Database

The app uses plain `sqlite3`. All tables are defined in
`automationv3/services/schema.sql`, which is applied (with `CREATE ... IF NOT
EXISTS`) every time the server starts. There are no migrations: to
change a table, edit `schema.sql`, delete the database file and reload the
sample data.

The database only holds the job queue and in-progress state. Finished runs
are plain files under `--reports-path` (default `./reports`): one uuidv7
folder per report, with one uuidv7 folder per run holding `run.json`,
`events.jsonl` and the exact `closure/` that was executed.
