#!/usr/bin/python3 

"""Automation Framework

Usage:
    automationv3 [--port PORT] [--dbpath PATH]
                 [--workspace_path PATH] [--debug]
    automationv3 (-h | --help)

Options:
    -h --help              show this help message and exit
    --port=PORT            tcp port to bind to [default: 8080]
    --dbpath=PATH          path to application database file 
                           [default: ./automationv3.db]
    --workspace_path=PATH  path to git repo [default: ./]
    --debug                enables autoload [default: false]

"""
__version__ = '3.0.0'
__banner__ = f"""\
                _                        _   _              __      ______  
     /\        | |                      | | (_)             \ \    / /___ \ 
    /  \  _   _| |_ ___  _ __ ___   __ _| |_ _  ___  _ __    \ \  / /  __) |
   / /\ \| | | | __/ _ \| '_ ` _ \ / _` | __| |/ _ \| '_ \    \ \/ /  |__ < 
  / ____ \ |_| | || (_) | | | | | | (_| | |_| | (_) | | | |    \  /   ___) |
 /_/    \_\__,_|\__\___/|_| |_| |_|\__,_|\__|_|\___/|_| |_|     \/   |____/ 

{'Version: ' + __version__ : >75} 
----------------------------------------------------------------------------
"""

import sqlite3
from pathlib import Path

from docopt import docopt
from waitress import serve
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from . import app
from ..models.workspace import Workspace

def start_server():
    
    arguments = docopt(__doc__, version=__version__)

    # TODO: Maybe use schema?
    port = int(arguments['--port'])
    workspace_path = Path(arguments['--workspace_path']).resolve()
    dbpath = Path(arguments['--dbpath']).resolve()
    debug = arguments['--debug'] 
    
    print(__banner__)
    
    app.config['DB_PATH'] = dbpath 
    app.config['WORKSPACE_PATH'] = workspace_path

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
        print(f'   Server started: http://localhost:{port}/')
        serve(app, port=port, threads=8)

    if debug:
        app.run(port=port, debug=True)
    else:
        print(f'   Server started: http://localhost:{port}/')
        serve(app, port=port, threads=8)



