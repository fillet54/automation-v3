
# DEMO

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
automation-v3 --workspace_path ./test/data/git_repos/master
```


## Generating Migrations

```
alembic revision -m "Add Worker"
```

Go edit migration in automationv3/database/migrations/versions. Then to
migrate run the following command:

```
alembic upgrade head
```
