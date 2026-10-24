"""Automation Framework

Usage:
    automation-v3 demo [--path PATH] [--port PORT] [--no-docs]
    automation-v3 server [--port PORT] [--dbpath PATH]
                         [--workspace-path PATH] [--reports-path PATH]
                         [--docs-path PATH] [--local-worker] [--config PATH]
                         [--settings PATH] [--debug]
    automation-v3 worker [--port PORT] [--config PATH]
                         [--central-server URL] [--no-http] [--debug]
    automation-v3 run SCRIPT... [--root PATH] [--config PATH]
                      [--env NAME]... [--variation NAME]... [--filter EXPR]
                      [--uut NAME=VERSION]... [--reports-path PATH]
    automation-v3 client [--port PORT] [--workspace-path PATH] [--server URL]
                         [--config PATH] [--data-path PATH] [--debug]
    automation-v3 login --server URL [--email EMAIL]
    automation-v3 logout [--server URL]
    automation-v3 whoami [--server URL]
    automation-v3 builds [--server URL]
    automation-v3 scratch SCRIPT... [--root PATH] [--server URL]
                          [--env NAME]... [--variation NAME]...
                          [--uut NAME=VERSION]...
                          [--no-wait]
    automation-v3 report edit REPORT [--title TEXT] [--number TEXT]
                         [--revision TEXT] [--author TEXT]
                         [--sign ROLE=NAME]... [--applicable DOC]...
                         [--reference DOC]...
    automation-v3 report export REPORT [--out DIR] [--template DIR]
    automation-v3 report reopen REPORT
    automation-v3 requirements import FOLDER... [--dbpath PATH]
    automation-v3 requirements log [--limit N] [--dbpath PATH]
    automation-v3 requirements history ID [--dbpath PATH]
    automation-v3 requirements diff FROM TO [--spec KEY]
                         [--subsystem NAME] [--dbpath PATH]
    automation-v3 (-h | --help)

Commands:
    demo                   set up a demo (sample scripts, requirements and
                           these docs) in a fresh folder, and serve it with
                           a worker. Deletes an earlier demo at --path
    server                 serve the web app and the job API, optionally
                           with a worker in the same process
    worker                 take jobs from a server and run them
    run                    run scripts on this machine, without a server
    client                 the local client's web UI, on this machine only:
                           your worktrees' scripts, checked as you write them,
                           run in scratch on the central server (or here,
                           with --config). Sign in first with login
    login                  sign this machine in to a central server: it
                           emails you a link to approve it
    logout                 sign this machine out, and revoke its token
    whoami                 who this machine is signed in as
    scratch                run scripts from your worktree in the central
                           server's scratch space, on its workers: in-work
                           edits included. Waits and prints each step.
                           With --uut NAME=local it uses your local build
                           of NAME, uploading it first if it isn't yet
    builds                 your local builds (see client.json), and whether
                           each is uploaded
    report edit            set a report's document fields: its title,
                           number, revision and author, who signs it, and
                           its applicable and reference documents
    report export          freeze a report and write its PDF and bundle,
                           report-<id>.zip
    report reopen          unfreeze an exported report, so runs can be
                           added to it again
    requirements import    import DOORS export folders, in order
    requirements log       the latest imports, and what each changed
    requirements history   every change to a requirement, and the
                           baselines it is in
    requirements diff      the requirements added, removed and changed
                           from one context to another: trunk, trunk@N
                           (as of import N), set:NAME (a baseline set)
                           or SPEC@BASELINE

Options:
    -h --help              show this help message and exit
    --port=PORT            tcp port to bind to [default: 8080]
    --dbpath=PATH          path to application database file
                           [default: ./automationv3.db]
    --workspace-path=PATH  path to git repo [default: ./] (not used when the
                           settings name a [git] remote to mirror)
    --reports-path=PATH    directory holding reports and runs
                           [default: ./reports]
    --docs-path=PATH       built HTML documentation to serve at /docs
    --path=PATH            the demo's folder [default: ./demo]
    --no-docs              don't build the documentation
    --central-server=URL   the central server: host:port, or a URL
    --config=PATH          worker config (JSON) naming the environments
                           it hosts
    --settings=PATH        server settings (TOML): sign-in, mail and a git
                           remote to mirror. Without it the server is
                           single-user
    --no-http              run the worker without its status page
    --local-worker         also run a worker inside the server process
                           (hosting the environments in --config)
    --root=PATH            root script path SCRIPTs are relative to
                           [default: ./]
    --server=URL           a central server (default: the one you last
                           signed in to)
    --email=EMAIL          your work email (asked for if not given)
    --no-wait              queue and print the runs' links, without waiting
    --data-path=PATH       where the client keeps its own scratch runs
                           (default: ~/.local/share/automation-v3/client)
    --env=NAME             environment to run in (default: all hosted)
    --variation=NAME       variation to run (default: all)
    --filter=EXPR          EDN predicate selecting variations
    --uut=NAME=VERSION     UUT version to use (default: newest)
    --debug                enables autoload [default: false]
    REPORT                 a report's folder (in the reports path)
    --title=TEXT           the report's name, its document's title
    --number=TEXT          the document's number
    --revision=TEXT        the document's revision
    --author=TEXT          the document's author
    --sign=ROLE=NAME       who signs for a role, e.g. "Approved by=J. Doe"
    --applicable=DOC       an applicable document, "NUMBER | REVISION | TITLE";
                           replaces the report's list
    --reference=DOC        a reference document, "NUMBER | REVISION | TITLE";
                           replaces the report's list
    --out=DIR              where to write the bundle (default: the report
                           folder's exports/)
    --template=DIR         the document template (default: the built-in one)
    FOLDER                 an export folder, holding manifest.json
    --limit=N              how many imports to show [default: 10]
    --spec=KEY             only this spec's requirements
    --subsystem=NAME       only this subsystem's requirements

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
    # A broken plugin is reported here, once, rather than by every script
    from .framework.plugins import PluginLoadError, load_plugins
    try:
        load_plugins()
    except PluginLoadError as e:
        sys.exit(f"{e}\nFix or uninstall the plugin, then start again.")
    if args["run"]:
        sys.exit(run(args))
    if args["login"] or args["logout"] or args["whoami"] or args["scratch"] \
            or args["builds"]:
        sys.exit(client_command(args))
    if args["report"]:
        sys.exit(report(args))
    if args["requirements"]:
        sys.exit(requirements(args))

    print(__banner__)
    if args["client"]:
        start_client(args)
    elif args["demo"]:
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


def serve(app, args, name, reload=True, host="0.0.0.0"):
    from waitress import serve

    if args["--debug"]:
        app.run(host=host, port=port(args), debug=True, use_reloader=reload)
    else:
        print(f"   {name} started: http://localhost:{port(args)}/")
        serve(app, host=host, port=port(args), threads=8)


def data_home():
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "automation-v3"


def start_client(args):
    """The local client's web UI, for this machine only (127.0.0.1)"""
    from .services import client
    from .services.database import connect, init_db
    from .web.app import create_app

    try:
        central = client.CentralClient.signed_in(args["--server"])
        me = central.whoami()
    except client.ClientError as e:
        sys.exit(str(e))
    workspace_path = Path(args["--workspace-path"]).resolve()
    if not workspace_path.exists():
        sys.exit("--workspace-path=PATH should exist")
    data = Path(args["--data-path"] or data_home() / "client").resolve()
    (data / "reports").mkdir(parents=True, exist_ok=True)
    db_path = data / "client.db"
    with closing(connect(db_path)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        init_db(conn)
    app = create_app(DB_PATH=db_path, WORKSPACE_PATH=workspace_path,
                     REPORTS_PATH=data / "reports", CENTRAL=central,
                     LOCAL_WORKER=bool(args["--config"]))
    print(f"   Signed in to {central.server} as {me['email']}")
    if args["--config"] and serving_process(args):
        start_local_worker(db_path, data / "reports", args["--config"])
    serve(app, args, "Client", host="127.0.0.1")


def start_server(args):
    from .services import settings as server_settings
    from .services.database import connect, init_db
    from .services.jobs import cleanup_finished
    from .web.app import create_app

    try:
        settings = server_settings.load(args.get("--settings"))
    except server_settings.SettingsError as e:
        sys.exit(str(e))

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
        SETTINGS=settings,
    )
    if settings.git is not None:
        from .services.mirror import MirrorError
        print(f"   Mirroring {settings.git.remote}")
        try:
            app.config["WORKSPACES"].refresh()
        except MirrorError as e:
            sys.exit(str(e))
        if not settings.git.webhook_secret:
            print("   No [git] webhook_secret: pushes show only when a report is queued")
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
    server = args["--central-server"]
    if "://" not in server:
        server = f"http://{server}"
    worker = Worker(
        ServerClient(server, self_url, token=worker_token(args["--config"])),
        Host.from_file(args["--config"]),
    )
    try:
        registered = worker.check_in(started=True)
    except PermissionError as e:
        sys.exit(f"{e}\nA central server needs a worker token: an admin makes one on "
                 "its Admin page; put it in the config as \"token\", or in "
                 "AUTOMATION_WORKER_TOKEN.")
    if not registered:
        sys.exit("Could not register with the central server")
    print("Registration successful")

    if args["--no-http"]:
        worker.work_forever()
    else:
        from .web.worker_app import create_worker_app

        worker.start()
        # No reloader: it would start the worker's threads a second time
        serve(create_worker_app(worker), args, "Worker", reload=False)


def worker_token(config):
    """The worker token: AUTOMATION_WORKER_TOKEN, else "token" in the
    worker's config file, else None"""
    import json
    if os.environ.get("AUTOMATION_WORKER_TOKEN"):
        return os.environ["AUTOMATION_WORKER_TOKEN"]
    if config:
        return json.loads(Path(config).read_text()).get("token")
    return None


class ConsoleObserver:
    """Prints each step of a local run as it happens"""

    def on_job(self, script, environment, variation, mode):
        where = ", ".join(x for x in (environment, variation) if x)
        print(f"\n{script}{' (' + where + ')' if where else ''}, {mode} mode")

    def on_step_end(self, form=None, passed=True, stdout="", stderr="",
                    precondition=False, error=False, placeholders=0, **kw):
        mark = ("TODO" if placeholders else "ok  ") if passed else \
            ("ERR " if error else "FAIL")
        label = "precondition " if precondition else ""
        shown = stdout.replace("\n", "\n         ") if stdout else ""
        print(f"  {mark} {label}step {kw.get('index')}{': ' + shown if shown else ''}")
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
        shown = shown.replace("\n", "\n" + indent + "     ")
        print(f"{indent}{mark} {label}{': ' + shown if shown else ''}")

    def on_cleanup(self, description=None, passed=True, message="", **kw):
        mark = "ok  " if passed else "ERR "
        print(f"  {mark} cleanup: {description}{': ' + message if message else ''}")

    def on_row_start(self, row=None, values=None, **kw):
        shown = ", ".join(f"{k}={v}" for k, v in (values or {}).items())
        print(f"    row {row}{': ' + shown if shown else ''}")

    def on_row_end(self, row=None, outcome=None, **kw):
        if outcome != "pass":
            print(f"    row {row} -> {outcome}")

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


def client_command(args):
    """login, logout, whoami and scratch: the local client. Returns the
    exit status."""
    from .services import client

    try:
        if args["login"]:
            server = client.normal_server(args["--server"])
            email = args["--email"] or input("Your work email: ").strip()
            email = client.CentralClient(server).login(email)
            print(f"Signed in to {server} as {email}")
            return 0
        central = client.CentralClient.signed_in(args["--server"])
        if args["logout"]:
            central.logout()
            print(f"Signed out of {central.server}")
            return 0
        if args["whoami"]:
            me = central.whoami()
            print(f"{me['email']} on {central.server}{' (admin)' if me['admin'] else ''}")
            return 0
        if args["builds"]:
            return list_builds(central)
        return scratch(args, central)
    except client.ClientError as e:
        print(e)
        return 2
    except KeyboardInterrupt:
        return 130


def scratch(args, central):
    """Upload scripts' closures from the worktree and run them in scratch"""
    from .services import client

    root = Path(args["--root"]).resolve()
    scripts = [
        str(Path(s).resolve().relative_to(root)) if Path(s).is_absolute() else s
        for s in args["SCRIPT"]
    ]
    files = client.upload_files(root, scripts)
    versions = local_versions(central, dict(uut.split("=", 1) for uut in args["--uut"]))
    environments = args["--env"] or [None]
    variations = args["--variation"] or [None]
    runs = []
    for environment in environments:
        for variation in variations:
            runs += central.scratch(client.current_branch(root), files, scripts,
                                    environment=environment, variation=variation,
                                    uut_versions=versions)
    for r in runs:
        print(f"Queued {r['script']}{where(r)}: {r['url']}")
    if args["--no-wait"]:
        return 0
    observer = ConsoleObserver()
    outcomes = []
    for r in runs:
        observer.on_job(r["script"], r.get("environment"), r.get("variation"), "scratch")
        outcome = central.follow(r["id"], lambda e: client.replay(observer, e))
        outcomes.append(outcome)
    print()
    for r, outcome in zip(runs, outcomes):
        print(f"  {outcome or 'not run':8} {r['script']}{where(r)}")
    return 0 if outcomes and all(o == "pass" for o in outcomes) else 1


def local_versions(central, versions):
    """`versions` with each NAME=local replaced by the version of your
    local build, uploaded first if it isn't yet"""
    from .framework.uut import uut_types
    from .services import builds, client

    server = None
    for uut, value in versions.items():
        if value != "local":
            continue
        build = builds.find_local_build(uut)
        if build is None:
            raise client.ClientError(f"No local {uut} build: set where they land in "
                                     f"{client.config_home() / 'client.json'}")
        server = server or central.uuts()
        uploaded = next((v["id"] for v in server.get(uut, [])
                         if v["digest"] == build.digest), None)
        if uploaded is None:
            print(f"Uploading your {uut} build {build.id}...")
            try:
                uploaded = uut_types()[uut]().upload_build(build).id
            except (RuntimeError, NotImplementedError, OSError) as e:
                raise client.ClientError(f"Couldn't upload the build: {e}") from None
        versions[uut] = uploaded
    builds.remember_used(versions)
    return versions


def list_builds(central):
    from .services import builds, client

    folders = builds.build_folders()
    if not folders:
        print(f"No build folders: say where each UUT's builds land in "
              f"{client.config_home() / 'client.json'}, e.g.\n"
              '  {"builds": {"demo": "~/work/demo/build/out"}}')
        return 1
    server = central.uuts()
    for uut, folder in sorted(folders.items()):
        build = builds.find_local_build(uut)
        if build is None:
            print(f"{uut}: no build in {folder}")
            continue
        uploaded = next((v["id"] for v in server.get(uut, [])
                         if v["digest"] == build.digest), None)
        state = f"uploaded as {uploaded}" if uploaded else "not uploaded yet"
        print(f"{uut}: {build.id} in {folder}, {state}")
    return 0


def where(run):
    shown = ", ".join(x for x in (run.get("environment"), run.get("variation")) if x)
    return f" ({shown})" if shown else ""


def report(args):
    """report edit, export and reopen. Returns the exit status."""
    from .services.reports import export, store

    folder = Path(args["REPORT"]).resolve()
    root, report_id = folder.parent, folder.name
    if store.load_report(root, report_id) is None:
        print(f"{folder} isn't a report folder: it has no report.json")
        return 2
    try:
        if args["edit"]:
            return edit_report(args, root, report_id)
        if args["reopen"]:
            export.reopen(root, report_id)
            print(f"Report {report_id} reopened")
            return 0
        report = store.load_report(root, report_id)
        missing = export.missing_fields(report)
        if missing:
            print(f"Warning: the report has no document {', '.join(missing)}; "
                  "set them with report edit")
        path = export.export(root, report_id, out_dir=args["--out"],
                             template=args["--template"])
    except export.ExportError as e:
        print(e)
        return 1
    print(f"Report {report_id} frozen\nWrote {path}")
    return 0


def requirements(args):
    """requirements import, log, history and diff. Returns the exit status."""
    from contextlib import closing

    from .services.database import connect, init_db
    from .services.requirements import export, models, store

    with closing(connect(args["--dbpath"])) as conn:
        init_db(conn)
        try:
            if args["import"]:
                for folder in args["FOLDER"]:
                    import_id, outcomes = store.import_export(conn, export.read(folder))
                    print(f"Import {import_id}: {folder}")
                    for label, outcome in outcomes:
                        print(f"  {label}: {outcome}")
            elif args["log"]:
                for import_id, at, source, changes in models.log(conn, int(args["--limit"])):
                    print(f"Import {import_id}, {at}: {source}")
                    for spec, id, what in changes:
                        print(f"  {spec} {id}: {', '.join(what)}")
            elif args["history"]:
                events = models.history(conn, args["ID"])
                if not events:
                    print(f"No requirement {args['ID']} has been imported")
                    return 1
                for e in events:
                    what = ", ".join(e.changes) if e.kind == "trunk" else "in baseline"
                    print(f"Import {e.import_id}, {e.imported_at}: {e.label}: {what}")
            else:
                changes = models.diff(conn, args["FROM"], args["TO"], spec=args["--spec"],
                                      subsystem=args["--subsystem"])
                for c in changes:
                    print(f"{c.spec} {c.id}: {', '.join(c.changes)}")
                print(f"{len(changes)} requirements differ")
        except (export.ExportError, models.ContextError) as e:
            print(e)
            return 1
    return 0


def edit_report(args, root, report_id):
    from .services.reports import export, store

    fields = {name: args[f"--{name}"] for name in ("title", "number", "revision", "author")
              if args[f"--{name}"] is not None}
    document = export.document_fields(store.load_report(root, report_id))
    if args["--sign"]:
        signatures = dict(document["signatures"])
        for sign in args["--sign"]:
            role, _, name = sign.partition("=")
            signatures[role.strip()] = name.strip()
        fields["signatures"] = signatures
    for kind in export.KINDS:
        if args[f"--{kind}"]:
            kept = [d for d in document["documents"] if d["kind"] != kind]
            fields["documents"] = kept + export.parse_documents(
                "\n".join(args[f"--{kind}"]), kind)
            document["documents"] = fields["documents"]
    export.set_document(root, report_id, **fields)
    document = export.document_fields(store.load_report(root, report_id))
    print(f"{document['title']}: {document['number'] or 'no number'}, revision "
          f"{document['revision'] or '-'}, by {document['author'] or '-'}")
    for role, name in document["signatures"].items():
        print(f"  {role}: {name}")
    for d in document["documents"]:
        print(f"  {d['kind']}: {d['number']} {d['revision']} {d['title']}")
    return 0
