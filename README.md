
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


## Database

The app uses plain `sqlite3`. All tables are defined in
`automationv3/database/schema.sql`, which is applied (with `CREATE ... IF NOT
EXISTS`) every time the server or worker starts. There are no migrations: to
change a table, edit `schema.sql`, delete the database file and reload the
sample data.
