
# Automation-v3

## Try the demo

From a clone of this repository, with Python 3.11 or newer:

```
python -m venv .venv
source .venv/bin/activate
pip install -e .
automation-v3 demo
```

The package is described by `pyproject.toml`. The UI's look (paper-ui)
and the docs' diagram renderer (mermaid-diag) are vendored in
`automationv3/vendor` (see the README there), so nothing else needs
checking out to run the app or build these docs.

Then open http://localhost:8080.

The demo tests the **Apollo lunar module**: a small simulation of its
powered descent and its guidance computer's software (Luminary), the `lm`
UUT in `automationv3/plugins/apollo`. Its example scripts and requirements
ship with the package, in `automationv3/examples/apollo`. Three versions of
the software are installed: `LUM099` (it has no extended missions, so
those runs are blocked), `LUM131` (with a defect invented for the example,
which one check catches on extended missions) and `LUM210` (fixed). The
mission (standard or extended) and where the flight starts (powered descent
initiation, high gate, low gate, the surface) are chosen at boot, so they
are variations: see `automationv3/examples/apollo/rvts/README.rst` for
what each script shows.

`demo` sets up everything in a fresh `./demo` folder and serves it, with a
worker in the same process:

- a workspace: a git repository of the example scripts on `master`, with
  three more branches as worktrees (`branch1` verifies Release 1);
- the example's requirements and their DOORS history (Release 1 for
  standard missions, Release 2 adding extended ones), loaded into the
  demo's database;
- the `sim` (stepped) and `lms` (the mission simulator, paced real time)
  environments, working under `demo/environments`;
- the lunar module's build repository (`demo/builds`), and in
  `demo/local-build` a build of LUM131 with its defect fixed, for the local
  client to find and upload;
- this project's documentation, built and linked as **Docs** in the
  app's navigation.

Each run deletes the earlier demo and starts again; it won't delete a
folder it didn't make. Use `--path` for another folder, `--port` for
another port, and `--no-docs` to skip building the documentation. The
documentation is built only from a source checkout.

To present it, `presentation/overview.html` is a short reveal.js deck
(the problem, the language, the app, requirements), and
`presentation/index.html` a detailed one of the framework's concepts and
its main workflows in the app.

## Running it yourself

1. Install as above and make a demo folder once (`automation-v3 demo`, then
   stop it): it holds a workspace, a database of requirements and a worker
   config.
2. Run the server on them:
```
automation-v3 server --workspace-path demo/workspace/master --dbpath demo/automationv3.db
```
3. Start a worker (in another terminal) to execute queued scripts. The
   config names the environments it hosts; this one hosts `sim` and `lms`.
```
automation-v3 worker --port 8081 --central-server localhost:8080 --config demo/worker.json
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
automation-v3 server --workspace-path demo/workspace/master --dbpath demo/automationv3.db --local-worker --config demo/worker.json
```

To serve the documentation at `/docs` (with a **Docs** link in the
navigation), build it and pass `--docs-path`:
```
make -C docs html
automation-v3 server --workspace-path demo/workspace/master --docs-path docs/_build/html
```

The docs' paragraphs use TeX line breaks, worked out in the reader's browser
(paper-ui's `line_breaks = "live"`); there is nothing to measure or commit.

### Running scripts without a server

`run` runs scripts on this machine, with no server or database, using the
same worker config. It prints each step, writes a normal report folder and
exits non-zero unless every run passed:

```
automation-v3 run LND/tc_lnd_001.rst --root automationv3/examples/apollo/rvts --config demo/worker.json --env sim
automation-v3 run ALM/tc_alm_003.rst --root automationv3/examples/apollo/rvts --config demo/worker.json --env sim --variation extended --uut lm=LUM131
```

The second fails on purpose: LUM131's defect.

## A central server and the local client

The server above is **single-user**: it reads local worktrees and nobody
signs in. For a team, give the server a settings file and it becomes
**central**. Everyone signs in with a link emailed to their work address
(no passwords). Scripts come from a mirror of the team's git remote, and
workers need a token an admin makes on the Admin page:

```toml
# server.toml
base_url = "https://automation.example.com"

[auth]
allowed_domains = ["example.com"]
admins = ["lead@example.com"]

[smtp]                      # without it, sign-in links are printed in the log
host = "mail.example.com"
sender = "automation@example.com"

[git]
remote = "git@git.example.com:team/scripts.git"
webhook_secret = "..."      # the git host's push webhook: POST /hooks/git
```
```
automation-v3 server --settings server.toml
automation-v3 worker --central-server https://automation.example.com --config worker.json   # "token" in worker.json
```

On each person's machine, the **client** works on their own worktrees and
sends scratch runs (edits included) and local builds to the central server:
```
automation-v3 login --server https://automation.example.com
automation-v3 client --workspace-path ~/work/scripts       # http://localhost:8080
automation-v3 scratch ALM/tc_alm_003.rst --uut lm=local
```
Reports run only what's pushed. Reports, Queue and Scratch show your own by
default, with an Everyone tab. See `docs/operating/deployment.rst`,
`accounts.rst` and `local-client.rst`.

## Code organization

Each layer only imports from the ones above it (`test/test_layers.py`
checks this):

| Package | Holds | Must not use |
| --- | --- | --- |
| `automationv3/framework` | The script language and its execution: edn, lisp, closures, preconditions, variations, planning, UUT/environment interfaces | storage, HTTP, Flask |
| `automationv3/documents` | Scripts, runs and reports as reStructuredText documents, rendered from data | storage, HTTP, Flask |
| `automationv3/lsp` | The language server: errors, completion and hover for scripts, in any editor | Flask, the web layer |
| `automationv3/services` | Concepts that need storage or processes: workspaces, requirements, reports, the job queue, workers | Flask, the web layer |
| `automationv3/web` | Flask pages and the HTTP job API, templates and static files | |
| `automationv3/cli.py` | `server`, `worker` and `run` | |
| `automationv3/plugins` | BuildingBlocks, UUTs and environments | services, web |

A worker takes jobs from anything with the small server interface in
`services/worker/worker.py`: the HTTP client (`services/worker/client.py`)
or `LocalServer` (`services/worker/local.py`), which `run` uses in-process.

A script is read once: `framework/source.py` parses the whole file with
docutils into one tree, in which `rvt` and `rvt-variant` are real
directives and `:req:` a role. Everything else is derived from that tree:
`source.statements`, the forms the executor, closures, static analysis and
the language server work from; `framework/cards.py`, the pieces the editor
edits (`build` and `placed` make the file from them again); and
`documents/script.py`, the page of a script, a picked variation or a run.

## Scripts

Scripts live in git, and the workspace page edits them in a worktree on
this machine (`docs/operating/editor.rst`). A script
is a reStructuredText (`.rst`) document whose code lives in `rvt`
directives; each form in an `rvt` block is a step, and the prose between
them is the script's documentation:

```rst
===========================
Ignition Waits For The Crew
===========================
At powered descent initiation the computer asks for the crew's consent.

Requirements
------------
1. :req:`LGC-GDN-001`

.. rvt::

   (Precondition "LM at PDI, the crew's part left to the script"
     (lm-ready-for? :standard :pdi :manual)
     :heal "Boot a standard mission at PDI with a manual crew"
     (boot-for :standard :pdi :manual))

Steps
-----

.. rvt:: Nothing happens without PRO

   (Verify dsky.flashing = true)
   (RunFor 30)
   (Verify engine.descent.on = false)

.. rvt:: PRO lights the engine

   (Proceed)
   (RunFor 1)
   (Verify deca.throttle = full-throttle)
```

Any `.rst` with an `rvt` block is a script (plain documents like a
README are only documentation). Each
folder (including the root) may hold a `core.rst` of shared definitions
(`def`, `defn`), only ever at the top level. A script loads the `core.rst` of every folder from the
root down to its own, then those of folders it imports with
`(import FOLDER)`. Inner definitions shadow outer ones; imports only add
definitions and never override a name the script's own chain defines.

BuildingBlocks are actions (do something), assertions (check something) or
values (read something), and only blocks fail steps: a step passes unless a
block it called failed, or something raised (an error). Its value is shown,
never judged, so checks are written as assertions:
`(Verify (landed-within-limits?))`. A block's `execute` gets its arguments
evaluated, except parameters it lists in `quoted` (Verify's operator); a
block that wants every form as written implements `execute_forms` instead.

Every name and call is checked before a script can be queued: unknown names,
names used before they are defined, arity, block syntax, definitions inside
other forms. Failures and findings are shown at the code that caused them,
with the offending form marked.

Scripts reference requirements with ``:req:`ID` `` in their documentation.
A script may declare variations, each binding the same symbols to
different values for its own run:

```clojure
(variations "mission start"
  ["standard from PDI"       [:standard :pdi]
   "extended from high gate" [:extended :high-gate]])
```

The queue dialog can untick variations or filter them with an EDN
predicate over those symbols plus `name` and `index`, e.g.
`(= mission :extended)`.

Preconditions state what must hold before the steps run, and may heal it:

```clojure
(Precondition "LM booted for the variation's mission, at its start point"
  (lm-ready? mission start)
  :heal "Boot the variation's mission at its start point"
  (boot mission start))
```

Workers run the job whose preconditions already hold (or heal) first,
leaving UUTs as they are between jobs. Only when no queued job is ready do
they start the UUTs fresh for the oldest one; a precondition that still
fails then makes the run **blocked**. Scripts reach a UUT through a handle
bound to its name, e.g. `(.mission lm)`.

`automationv3/examples/apollo/rvts` is the example set: it tests the lunar
module's requirements, and its `README.rst` lists what each script shows
and which ones fail on purpose.

A script can define things too. Definitions are never reported as steps;
a script's definitions section (an `rvt` block with the `:definitions:`
option, placed before any step) loads with the closure, and pages show it
collapsed:

```rst
.. rvt::
   :definitions:

   (def approach-deg 25)
```

Blocks compose in scripts. Wherever a block is called (top level, a `defn`,
a `let`), it is reported, and a failure stops the script.
`(step "title" ...)` groups calls under one entry, `(try-ok? (Block ...))`
and `(try form default)` suppress failures explicitly, and `(quietly ...)`
leaves calls out of the output:

```clojure
(defn land-and-keep [label]
  (step "Fly to touchdown and attach the trajectory"
    (FlyTo :touchdown)
    (AttachTrajectory label)))
```

Steps render through their BuildingBlock: a block can override `as_html`
(or `as_rst`) to show its arguments readably, e.g. a configuration as a
table; otherwise the step shows as code.

`(environments :sim ...)` and `(uut :lm ...)` declare where a script can
run and what it tests. They are inherited from the `core.rst` chain and the
script can override them. UUTs and environments are plugins in
`automationv3/plugins` (see `plugins/apollo`).


## Database

The app uses plain `sqlite3`. All tables are defined in
`automationv3/services/schema.sql`, which is applied (with `CREATE ... IF NOT
EXISTS`) every time the server starts. There are no migrations: to
change a table, edit `schema.sql`, delete the database file and make the
demo again.

The database holds the job queue and in-progress state, the requirements,
and on a central server the accounts (only hashes of sign-in links, sessions
and tokens). Finished runs
are plain files under `--reports-path` (default `./reports`): one uuidv7
folder per report, with one uuidv7 folder per run holding `run.json`,
`events.jsonl` and the exact `closure/` that was executed.
