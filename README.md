
# Automation-v3

## Quick Start
1. Create virtual env
```
python -m venv .venv
source .venv/bin/activate.sh
```
2. Install dependencies
```
pip install -r requirements.txt
python setup.py develop
```
3. Create sample db
```
python test/data/load_sample.py
```
4. Create sample workspace
```
python test/data/makeworspaces.py
```
5. Run!
```
automation-v3 server --workspace-path ./test/data/git_repos/master
```
6. Start a worker (in another terminal) to execute queued scripts. The
   config names the environments it hosts; this one hosts the sample `sim`.
```
automation-v3 worker --port 8081 --central-server localhost:8080 --config test/data/worker-sim.json
```
Pick requirements on the **Requirements** page (or open a script and press
**Queue…**), choose environments, UUT versions and variations, and queue.
The report rolls each requirement up as Green (every linked script passed
in every environment and variation), Red (any failed) or Partial.

## Scripts

Scripts are authored in git; the workspace is a read-only viewer. Each
folder (including the root) may hold a `core.rvt`, the only place `def` and
`defn` are allowed. A script loads the `core.rvt` of every folder from the
root down to its own, then those of folders it imports with
`(import FOLDER)`. Inner definitions shadow outer ones; imports only add
definitions and never override a name the script's own chain defines. A step whose head is
a `defn` is called with evaluated arguments and passes if it returns
something truthy; every other step runs through its BuildingBlock.

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

`(environments :sim ...)` and `(uut :demo ...)` declare where a script can
run and what it tests. They are inherited from the `core.rvt` chain and the
script can override them. UUTs and environments are plugins in
`automationv3/plugins` (see `plugins/sample`).


## Database

The app uses plain `sqlite3`. All tables are defined in
`automationv3/database/schema.sql`, which is applied (with `CREATE ... IF NOT
EXISTS`) every time the server starts. There are no migrations: to
change a table, edit `schema.sql`, delete the database file and reload the
sample data.

The database only holds the job queue and in-progress state. Finished runs
are plain files under `--reports-path` (default `./reports`): one uuidv7
folder per report, with one uuidv7 folder per run holding `run.json`,
`events.jsonl` and the exact `closure/` that was executed.
