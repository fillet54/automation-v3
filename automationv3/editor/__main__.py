#!/usr/bin/python3 

"""Automation Framework

Usage:
    automation-v3 [--port PORT] [--dbpath PATH]
                  [--workspace_path PATH] [--debug]
    automation-v3 (-h | --help)

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

import os
import sqlite3
from pathlib import Path

from docopt import docopt
from schema import Schema, And, Use, SchemaError
from waitress import serve
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from . import app
from .workspace import Workspace

def start_server():
    
    args = docopt(__doc__, version=__version__)

    # arguments/options schema
    schema = Schema({
        '--port': And(Use(int), lambda p: 0 < p <= 65535,
                      error="--port=PORT should be positive integer < 65535"),
        '--dbpath': And(os.path.exists, error='--dbpath=PATH should exists'),
        '--workspace_path': And(os.path.exists, 
                                error='--workspace_path=PATH should exists'),
        '--debug': bool,
        '--help': bool
    })
    
    try:
        args = schema.validate(args)
    except SchemaError as e:
        exit(e)

    print(__banner__)
    
    app.config['DB_PATH'] = Path(args['--dbpath']).resolve()
    app.config['WORKSPACE_PATH'] = Path(args['--workspace_path']).resolve()

    engine = create_engine(f"sqlite:///{app.config['DB_PATH']}")
    app.config['DB_ENGINE'] = engine
    app.config['DB_SESSION_MAKER'] = sessionmaker(engine)

    # Create DB and enable WAL
    sqlite_conn = sqlite3.connect(app.config['DB_PATH'])
    sqlite_conn.execute('PRAGMA journal_mode=WAL')

    # Initialize/Create DBs
    Workspace.ensure_db(sqlite_conn)

    if args['--debug']:
        app.run(port=args['--port'], debug=True)
    else:
        print(f'   Server started: http://localhost:{args["--port"]}/')
        serve(app, port=args['--port'], threads=8)




