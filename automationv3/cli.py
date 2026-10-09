"""Automation Framework

Usage:
    automation-v3 demo [--path PATH] [--port PORT] [--no-docs]
    automation-v3 server [--port PORT] [--dbpath PATH]
                         [--workspace-path PATH] [--reports-path PATH]
                         [--docs-path PATH] [--local-worker] [--config PATH]
                         [--debug]
    automation-v3 worker [--port PORT] [--config PATH]
                         [--central-server URL] [--no-http] [--debug]
    automation-v3 run SCRIPT... [--root PATH] [--config PATH]
                      [--env NAME]... [--variation NAME]... [--filter EXPR]
                      [--uut NAME=VERSION]... [--reports-path PATH]
    automation-v3 (-h | --help)

Commands:
    demo                   set up a demo (sample scripts, requirements and
                           these docs) in a fresh folder, and serve it with
                           a worker. Deletes an earlier demo at --path
    server                 serve the web app and the job API, optionally
                           with a worker in the same process
    worker                 take jobs from a server and run them
    run                    run scripts on this machine, without a server

Options:
    -h --help              show this help message and exit
    --port=PORT            tcp port to bind to [default: 8080]
    --dbpath=PATH          path to application database file
                           [default: ./automationv3.db]
    --workspace-path=PATH  path to git repo [default: ./]
    --reports-path=PATH    directory holding reports and runs
                           [default: ./reports]
    --docs-path=PATH       built HTML documentation to serve at /docs
    --path=PATH            the demo's folder [default: ./demo]
    --no-docs              don't build the documentation
    --central-server=URL   host:port of the central server
    --config=PATH          worker config (JSON) naming the environments
                           it hosts
    --no-http              run the worker without its status page
    --local-worker         also run a worker inside the server process
                           (hosting the environments in --config)
    --root=PATH            root script path SCRIPTs are relative to
                           [default: ./]
    --env=NAME             environment to run in (default: all hosted)
    --variation=NAME       variation to run (default: all)
    --filter=EXPR          EDN predicate selecting variations
    --uut=NAME=VERSION     UUT version to use (default: newest)
    --debug                enables autoload [default: false]

"""
from . import __version__
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
import sys
from contextlib import closing
from pathlib import Path

from docopt import docopt


def main(argv=None):
    args = docopt(__doc__, argv=argv, version=__version__)
    if args["run"]:
        sys.exit(run(args))

    print(__banner__)
    if args["demo"]:
        start_demo(args)
    elif args["server"]:
        start_server(args)
    else:
        start_worker(args)


def port(args):
    value = int(args["--port"])
    if not 0 < value <= 65535:
        sys.exit("--port=PORT should be positive integer < 65535")
    return value


def serve(app, args, name, reload=True):
    from waitress import serve

    if args["--debug"]:
        app.run(port=port(args), debug=True, use_reloader=reload)
    else:
        print(f"   {name} started: http://localhost:{port(args)}/")
        serve(app, port=port(args), threads=8)


def start_server(args):
    from .services.database import connect, init_db
    from .services.jobs import cleanup_finished
    from .web.app import create_app

    db_path = Path(args["--dbpath"]).resolve()
    reports_path = Path(args["--reports-path"]).resolve()
    workspace_path = Path(args["--workspace-path"]).resolve()
    parents = ((db_path.parent, "--dbpath"), (reports_path.parent, "--reports-path"))
    for path, flag in parents:
        if not path.is_dir():
            sys.exit(f"{flag}=PATH should be in an existing directory")
    if not workspace_path.exists():
        sys.exit("--workspace-path=PATH should exist")
    reports_path.mkdir(exist_ok=True)

    with closing(connect(db_path)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        init_db(conn)
        cleanup_finished(conn, reports_path)

    docs_path = args.get("--docs-path")
    if docs_path and not (Path(docs_path) / "index.html").exists():
        sys.exit("--docs-path=PATH should hold built HTML (an index.html)")

    app = create_app(
        DB_PATH=db_path, WORKSPACE_PATH=workspace_path, REPORTS_PATH=reports_path,
        DOCS_PATH=Path(docs_path).resolve() if docs_path else None,
    )
    if args["--local-worker"] and serving_process(args):
        start_local_worker(db_path, reports_path, args["--config"])
    serve(app, args, "Server")


def start_demo(args):
    """Set up a fresh demo and serve it, with a worker in-process"""
    from .demo import DemoError, setup

    try:
        demo = setup(args["--path"], docs=not args["--no-docs"])
    except DemoError as e:
        sys.exit(str(e))
    start_server({
        **args,
        "--dbpath": demo.db_path,
        "--workspace-path": demo.workspace,
        "--reports-path": demo.reports,
        "--docs-path": demo.docs,
        "--config": demo.config,
        "--local-worker": True,
    })


def serving_process(args):
    """False in the --debug reloader's watcher process, which never serves"""
    return not args["--debug"] or os.environ.get("WERKZEUG_RUN_MAIN") == "true"


def start_local_worker(db_path, reports_path, config):
    """A worker taking jobs straight from the server's database"""
    from .services.worker import Host, Worker
    from .services.worker.local import LocalServer

    url = f"local://{socket.gethostname()}"
    worker = Worker(LocalServer(db_path, reports_path, url), Host.from_file(config))
    worker.start()
    hosted = ", ".join(worker.host.environments) or "no environments"
    print(f"   Local worker started: {url} ({hosted})")
    return worker


def start_worker(args):
    from .services.worker import Host, Worker
    from .services.worker.client import ServerClient

    if not args["--central-server"]:
        sys.exit("--central-server=URL is required")
    self_url = f"http://{socket.gethostname()}:{port(args)}"
    worker = Worker(
        ServerClient(f"http://{args['--central-server']}", self_url),
        Host.from_file(args["--config"]),
    )
    if not worker.check_in(started=True):
        sys.exit("Could not register with the central server")
    print("Registration successful")

    if args["--no-http"]:
        worker.work_forever()
    else:
        from .web.worker_app import create_worker_app

        worker.start()
        # No reloader: it would start the worker's threads a second time
        serve(create_worker_app(worker), args, "Worker", reload=False)


class ConsoleObserver:
    """Prints each step of a local run as it happens"""

    def on_job(self, script, environment, variation, mode):
        where = ", ".join(x for x in (environment, variation) if x)
        print(f"\n{script}{' (' + where + ')' if where else ''}, {mode} mode")

    def on_step_end(self, form=None, passed=True, stdout="", stderr="",
                    precondition=False, error=False, **kw):
        mark = "ok  " if passed else ("ERR " if error else "FAIL")
        label = "precondition " if precondition else ""
        print(f"  {mark} {label}step {kw.get('index')}"
              f"{': ' + stdout if stdout else ''}")
        if stderr:
            print("       " + stderr.strip().replace("\n", "\n       "))

    def on_call_start(self, form=None, call=None, **kw):
        self.forms = getattr(self, "forms", {})
        self.forms[call] = form

    def on_call_end(self, passed=True, stdout="", depth=0, quiet=False,
                    suppressed=False, error=False, title=None, value=None, call=None,
                    **kw):
        if quiet:
            return
        if suppressed:
            mark = "yes " if passed else "no  "
        else:
            mark = "ok  " if passed else ("ERR " if error else "FAIL")
        indent = "      " + "  " * depth
        label = title or self.forms.get(call)
        shown = stdout or (f"-> {value}" if value is not None else "")
        print(f"{indent}{mark} {label}{': ' + shown if shown else ''}")

    def on_procedure_end(self, outcome=None, **kw):
        print(f"  -> {outcome}")

    def on_error(self, traceback=None, **kw):
        print(traceback)


def run(args):
    """Run scripts locally. Returns the exit status: 0 if every run passed."""
    from .services.jobs import QueueError
    from .services.reports import store
    from .services.worker import Host
    from .services.worker.local import run_locally

    root = Path(args["--root"]).resolve()
    scripts = [
        str(Path(s).resolve().relative_to(root)) if Path(s).is_absolute() else s
        for s in args["SCRIPT"]
    ]
    variations = None
    if args["--variation"]:
        variations = {f"{s}::{v}" for s in scripts for v in args["--variation"]}
    versions = dict(uut.split("=", 1) for uut in args["--uut"])
    reports_path = Path(args["--reports-path"]).resolve()
    reports_path.mkdir(exist_ok=True)

    try:
        report_id, plan = run_locally(
            root, scripts, reports_path,
            host=Host.from_file(args["--config"]),
            environments=args["--env"] or None,
            variations=variations,
            filter_source=args["--filter"] or "",
            versions=versions,
            observers=[ConsoleObserver()],
        )
    except QueueError as e:
        print("Nothing could run:\n  " + "\n  ".join(e.errors))
        return 2

    runs = store.list_runs(reports_path, report_id)
    print(f"\nReport {report_id} in {reports_path}")
    for s in plan.scripts:
        if s.skipped:
            print(f"  skipped {s.script}: {s.skipped}")
    for r in runs:
        variation = (r.get("variation") or {}).get("name")
        where = ", ".join(x for x in (r.get("environment"), variation) if x)
        print(f"  {r.get('outcome') or 'not run':8} {r['script']}"
              f"{' (' + where + ')' if where else ''}")
    passed = runs and all(r.get("outcome") == "pass" for r in runs)
    return 0 if passed else 1
