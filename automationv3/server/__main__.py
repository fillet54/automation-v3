import click
from pathlib import Path
from waitress import serve
import sqlite3
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from . import app

from ..models.workspace import Workspace

@click.command()
@click.option('--port', default=8080, help="HTTP port number")
@click.option('--dbpath', default='./automationv3.db', help="HTTP port number")
@click.option('--workspace_path', default='./', help="Should point to git repo")
@click.option('--debug', is_flag=True, help="Run in debug mode")
def start_server(port, dbpath, workspace_path, debug):
    print(f"""\
                _                        _   _              __      ______  
     /\        | |                      | | (_)             \ \    / /___ \ 
    /  \  _   _| |_ ___  _ __ ___   __ _| |_ _  ___  _ __    \ \  / /  __) |
   / /\ \| | | | __/ _ \| '_ ` _ \ / _` | __| |/ _ \| '_ \    \ \/ /  |__ < 
  / ____ \ |_| | || (_) | | | | | | (_| | |_| | (_) | | | |    \  /   ___) |
 /_/    \_\__,_|\__\___/|_| |_| |_|\__,_|\__|_|\___/|_| |_|     \/   |____/ 

                                                             Version: 3.0.0
----------------------------------------------------------------------------

    Server started: http://localhost:{port}/


    """)

    app.config['DB_PATH'] = Path(dbpath).resolve()
    app.config['WORKSPACE_PATH'] = Path(workspace_path).resolve()

    engine = create_engine(f"sqlite:///{app.config['DB_PATH']}")
    app.config['DB_ENGINE'] = engine
    app.config['DB_SESSION_MAKER'] = sessionmaker(engine)


    # Create DB and enable WAL
    sqlite_conn = sqlite3.connect(app.config['DB_PATH'])
    sqlite_conn.execute('PRAGMA journal_mode=WAL')

    # Initialize/Create DBs
    Workspace.ensure_db(sqlite_conn)


    if debug:
        app.run(port=port, debug=True)
    else:
        serve(app, port=port, threads=8)



