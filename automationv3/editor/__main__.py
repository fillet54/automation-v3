#!/usr/bin/python3

"""Automation Framework

Usage:
    automation-v3 server [--port PORT] [--dbpath PATH]
                         [--workspace-path PATH] [--debug]
    automation-v3 worker [--port PORT] [--dbpath PATH]
                         [--central-server URL] [--debug]
    automation-v3 (-h | --help)

Options:
    -h --help              show this help message and exit
    --port=PORT            tcp port to bind to [default: 8080]
    --dbpath=PATH          path to application database file
                           [default: ./automationv3.db]
    --workspace-path=PATH  path to git repo [default: ./]
    --central-server=URL   url to central server
    --debug                enables autoload [default: false]

"""
__version__ = "3.0.0"
__banner__ = (
    r"""\
                _                        _   _              __      ______
     /\        | |                      | | (_)             \ \    / /___ \
    /  \  _   _| |_ ___  _ __ ___   __ _| |_ _  ___  _ __    \ \  / /  __) |
   / /\ \| | | | __/ _ \| '_ ` _ \ / _` | __| |/ _ \| '_ \    \ \/ /  |__ <
  / ____ \ |_| | || (_) | | | | | | (_| | |_| | (_) | | | |    \  /   ___) |
 /_/    \_\__,_|\__\___/|_| |_| |_|\__,_|\__|_|\___/|_| |_|     \/   |____/

"""
    + f"""{'Version: ' + __version__ : >75}
----------------------------------------------------------------------------
"""
)

import os
import sqlite3
from pathlib import Path
from contextlib import closing

from docopt import docopt
from schema import Schema, And, Or, Use, SchemaError
from waitress import serve
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def main():
    args = docopt(__doc__, version=__version__)

    # arguments/options schema
    schema = Schema(
        {
            "--port": And(
                Use(int),
                lambda p: 0 < p <= 65535,
                error="--port=PORT should be positive integer < 65535",
            ),
            "--dbpath": And(os.path.exists, error="--dbpath=PATH should exists"),
            "--workspace-path": And(
                os.path.exists, error="--workspace-path=PATH should exists"
            ),
            "--central-server": Or(str, None),
            "server": bool,
            "worker": bool,
            "--debug": bool,
            "--help": bool,
        }
    )

    try:
        args = schema.validate(args)
    except SchemaError as e:
        exit(e)

    print(__banner__)

    if args["server"]:
        start_server(args)
    else:
        start_worker(args)


def setup_db_config(app, args):
    engine = create_engine(f"sqlite:///{app.config['DB_PATH']}")
    app.config["DB_ENGINE"] = engine
    app.config["DB_SESSION_MAKER"] = sessionmaker(engine)

    # Create DB and enable WAL
    with closing(sqlite3.connect(app.config["DB_PATH"])) as conn:
        conn.execute("PRAGMA journal_mode=WAL")


def start_worker(args):
    from ..jobqueue.worker import app, register_worker

    app.config["DB_PATH"] = Path(args["--dbpath"]).resolve()
    app.config["CENTRAL_SERVER_URL"] = args["--central-server"]
    app.config["WORKER_URL"] = f"http://{args['--central-server']}/runner/workers"

    setup_db_config(app, args)

    register_worker()
    if args["--debug"]:
        app.run(port=args["--port"], debug=True)
    else:
        print(f'   Worker started: http://localhost:{args["--port"]}/')
        serve(app, port=args["--port"], threads=8)


def start_server(args):
    from . import app
    from .workspace import Workspace

    app.config["DB_PATH"] = Path(args["--dbpath"]).resolve()
    app.config["WORKSPACE_PATH"] = Path(args["--workspace-path"]).resolve()

    setup_db_config(app, args)

    # Initialize/Create DBs
    with closing(sqlite3.connect(app.config["DB_PATH"])) as conn:
        Workspace.ensure_db(conn)

    if args["--debug"]:
        app.run(port=args["--port"], debug=True)
    else:
        print(f'   Server started: http://localhost:{args["--port"]}/')
        serve(app, port=args["--port"], threads=8)
