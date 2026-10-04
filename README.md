
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
6. Start a worker (in another terminal) to execute queued scripts
```
automation-v3 worker --port 8081 --central-server localhost:8080
```
Open a script and press **Run Test**; the run page updates as the worker
executes it.


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
