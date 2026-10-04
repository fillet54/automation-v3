#!/usr/bin/python3

"""Automation Framework

Usage:
    automation-v3 server [--port PORT] [--dbpath PATH]
                         [--workspace-path PATH] [--reports-path PATH]
                         [--debug]
    automation-v3 worker [--port PORT] [--config PATH]
                         [--central-server URL] [--debug]
    automation-v3 (-h | --help)

Options:
    -h --help              show this help message and exit
    --port=PORT            tcp port to bind to [default: 8080]
    --dbpath=PATH          path to application database file
                           [default: ./automationv3.db]
    --workspace-path=PATH  path to git repo [default: ./]
    --reports-path=PATH    directory holding reports and runs
                           [default: ./reports]
    --central-server=URL   url to central server
    --config=PATH          worker config (JSON) naming the environments
                           it hosts
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
import socket
from pathlib import Path
from contextlib import closing

from docopt import docopt
from schema import Schema, And, Or, Use, SchemaError
from waitress import serve

from .database import connect, init_db
from .jobqueue.models import cleanup_finished


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
            "--dbpath": And(
                lambda p: Path(p).resolve().parent.is_dir(),
                error="--dbpath=PATH should be in an existing directory",
            ),
            "--workspace-path": And(
                os.path.exists, error="--workspace-path=PATH should exists"
            ),
            "--reports-path": And(
                lambda p: Path(p).resolve().parent.is_dir(),
                error="--reports-path=PATH should be in an existing directory",
            ),
            "--central-server": Or(str, None),
            "--config": Or(
                None,
                And(os.path.isfile, error="--config=PATH should be a file"),
            ),
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


def setup_db(app):
    with closing(connect(app.config["DB_PATH"])) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        init_db(conn)


def start_worker(args):
    from .jobqueue.worker import app, start_worker_threads

    app.config["SERVER_URL"] = f"http://{args['--central-server']}"
    app.config["SELF_URL"] = f"http://{socket.gethostname()}:{args['--port']}"
    app.config["CONFIG_PATH"] = args["--config"]

    start_worker_threads()
    if args["--debug"]:
        app.run(port=args["--port"], debug=True)
    else:
        print(f'   Worker started: http://localhost:{args["--port"]}/')
        serve(app, port=args["--port"], threads=8)


def start_server(args):
    from .app import app

    app.config["DB_PATH"] = Path(args["--dbpath"]).resolve()
    app.config["WORKSPACE_PATH"] = Path(args["--workspace-path"]).resolve()
    app.config["REPORTS_PATH"] = Path(args["--reports-path"]).resolve()
    app.config["REPORTS_PATH"].mkdir(exist_ok=True)

    setup_db(app)
    with closing(connect(app.config["DB_PATH"])) as conn:
        cleanup_finished(conn, app.config["REPORTS_PATH"])

    if args["--debug"]:
        app.run(port=args["--port"], debug=True)
    else:
        print(f'   Server started: http://localhost:{args["--port"]}/')
        serve(app, port=args["--port"], threads=8)


if __name__ == "__main__":
    main()
