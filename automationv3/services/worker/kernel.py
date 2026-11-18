"""The console's kernel: a long-lived interpreter on this machine

A Kernel keeps what a run builds and then throws away: the script's
Lisp env (its core.rst chain, its definitions, its variation's
symbols), the UUT handles and the environment's clock. Commands sent to
it, a card or some forms, run in that env one at a time, on the
kernel's own thread, as a script's statements run (executor.py): the
same steps, preconditions, tables and block calls. What they did comes
back as a transcript: short lines, made from the run's events as they
happen (Transcript).

Nothing a kernel does is recorded: it makes no runs and no reports.

The kernel borrows a Host (the local worker's), so its UUTs are the
same ones the worker runs jobs on; whoever makes a kernel keeps the
worker off them meanwhile (Worker.borrow).

- open: attach to the UUTs as they are when the versions asked for are
  installed, else install and start them fresh, as force mode does;
  then build the env.
- reset: release what is held (the cleanups of SetFixedValue and
  such), and build the env again from the files as they are now. The
  UUTs aren't touched.
- restart: reset, then install (if needed) and start every UUT fresh.
- release: run the cleanups only.
- stop: the command running stops at its next check (context.Stopped);
  the kernel goes on.

Everything but stop is queued and runs on the kernel's thread, in
order. A command stuck in code that never checks for a stop can't be
stopped: restart(abandon=True) leaves its thread behind (a daemon) and
carries on with a new one.
"""

import itertools
import queue
import re
import threading
import time
import traceback
from pathlib import Path

from ...framework import clock as clocks
from ...framework import closure as closures
from ...framework import context, edn, executor
from ...framework.language import is_definition, is_step
from .worker import handles, install_uuts, versions_installed

CARD = "<card>"  # the path a card's statements are read as
MAX_LINES = 2000  # transcript lines kept
MAX_OUTCOMES = 100  # command outcomes kept
SHORT = 100  # characters of a form shown on one line
FOLD = 5  # output lines shown before folding the rest


class KernelError(Exception):
    """A kernel can't be made, or can't do what was asked"""


def short(text, width=SHORT):
    """`text` on one line, cut to `width`"""
    one = " ".join(str(text).split())
    return one if len(one) <= width else one[:width - 1] + "…"


PRECONDITION_TEXT = re.compile(r'^\(Precondition\s+"((?:[^"\\]|\\.)*)"')


def label(text):
    """How a form is named on one line: a Precondition by its description"""
    found = PRECONDITION_TEXT.match(text.strip())
    return f"Precondition: {found.group(1)}" if found else text


def described(value, source=None):
    """{kind, value}: what a name is, and its value on one line"""
    from ...framework.refs import Ref
    if source == "uut":
        return {"kind": "uut", "value": type(value).__name__}
    if isinstance(value, Ref):
        return {"kind": "ref", "value": f"{type(value).__name__.lower()} {value.path}"}
    if callable(value):
        signatures = getattr(value, "signatures", None)
        if signatures is not None:
            shown = " ".join(edn.writes(params) for params in signatures)
            return {"kind": "fn", "value": f"(fn {shown})"}
        return {"kind": "fn", "value": getattr(value, "__name__", "function")}
    try:
        shown = edn.writes(value)
    except Exception:
        shown = repr(value)
    kind = ("map" if isinstance(value, dict) else "vector" if isinstance(value, list)
            else "value")
    return {"kind": kind, "value": short(shown, 120)}


def newest(uut):
    versions = uut.list_versions()
    return versions[-1] if versions else None


class Command:
    _ids = itertools.count(1)

    def __init__(self, kind, **details):
        self.id = next(self._ids)
        self.kind = kind  # card, forms, reset, restart, release, open
        self.details = details
        self.outcome = None


class Transcript:
    """An observer turning a command's events into transcript lines.

    A line is {n, command, kind, text, ...}: kinds are command, step,
    call, out, fail, result, row, phase, ref, file, note and error. A
    step's line is written when it ends, with the calls it made and their
    output under it, so lines are never changed once written; what is
    running now is the kernel's state (`running`)."""

    def __init__(self, kernel, command, place):
        self.kernel, self.command = kernel, command
        self.place = place  # (span) -> {line, character} in the card, or None
        self.calls = []
        self.forms = {}  # call -> its form, between its start and end
        self.refs = []
        self.phases = []

    def __getattr__(self, name):
        if name.startswith("on_"):  # events it doesn't show
            return lambda **kw: None
        raise AttributeError(name)

    def add(self, kind, text, **details):
        self.kernel.add_line(self.command, kind, text, **details)

    def on_procedure_begin(self, **kw):
        pass

    def on_step_start(self, form, index, precondition=False, **kw):
        self.form = label(form) if precondition else form
        self.calls, self.refs, self.phases = [], [], []
        self.kernel.running = short(form)

    def on_call_start(self, form, call=None, **kw):
        self.forms[call] = form

    def on_call_end(self, passed, call=None, stdout="", depth=0, quiet=False,
                    title=None, duration=0, **kw):
        form = self.forms.pop(call, "")
        if quiet:
            return
        self.calls.append((depth, title or form, passed, stdout, duration))

    def on_phase_end(self, action, passed, **kw):
        self.phases.append(f"{action} {'✓' if passed else '✗'}")

    def on_ref(self, path, name, operation, **kw):
        if (operation, name) not in self.refs:
            self.refs.append((operation, name))

    def on_attach(self, name, data, **kw):
        stored = self.kernel.store_file(name, data)
        self.add("file", name, file=stored)

    def on_table_start(self, rows, **kw):
        pass

    def on_row_start(self, row, values, **kw):
        shown = ", ".join(f"{k} {v}" for k, v in values.items())
        self.add("row", f"row {row}" + (f" ({short(shown, 60)})" if shown else ""))

    def on_row_end(self, row, outcome, message="", **kw):
        if outcome != "pass":
            self.add("fail", f"row {row}: {outcome}" + (f": {message}" if message else ""))

    def on_step_end(self, passed, stdout="", stderr="", duration=0,
                    message="", trace=(), placeholders=0, definition=False,
                    precondition=False, error=False, printed="", **kw):
        self.kernel.running = None
        if definition:  # only a definition that failed is reported
            self.add("fail", message or "the definition failed", **self.where(trace))
            return
        mark = "…" if passed and placeholders else ("✓" if passed else "✗")
        self.add("step", f"{mark} {short(self.form or '', SHORT)}",
                 passed=bool(passed), duration=duration, tbd=bool(placeholders))
        if printed:  # what it printed comes first in its stdout too
            stdout = stdout[len(printed):].lstrip("\n") if stdout.startswith(printed) else stdout
            self.output(printed, 0, kind="printed")
        if self.phases:
            self.add("phase", ", ".join(self.phases))
        for depth, form, ok, out, took in self.calls:
            self.add("call", f"{'✓' if ok else '✗'} {short(form)}", depth=depth,
                     passed=bool(ok), duration=took)
            self.output(out, depth + 1)
        if not self.calls or not passed:
            self.output(stdout if not stdout.startswith("returned ") else "", 0)
        operations = {}
        for operation, name in self.refs:
            operations.setdefault(operation, []).append(name)
        for operation, names in operations.items():
            self.add("ref", f"{operation}: {', '.join(names)}")
        if placeholders:
            self.add("note", "not written yet (TBD)")
        if not passed and self.kernel.stop_event.is_set() and "Stopped" in (message or ""):
            return  # the kernel says it stopped
        if not passed:
            self.add("fail", message or "failed", **self.where(trace))
            plain = "unknown name" in message or message.startswith("No BuildingBlock")
            if error and stderr and "Traceback" in stderr and not plain:
                self.add("error", stderr.strip())

    form = None

    def where(self, trace):
        """{at: {line, character}} of the innermost place in the card a
        failure came through, or {at_text: "core.rst:12"} if none"""
        for span in trace or ():
            at = self.place(span)
            if at is not None:
                return {"at": at}
        for span in trace or ():
            if span.get("source"):
                return {"at_text": f"{span['source']}:{span['line']}"}
        return {}

    def output(self, text, depth, kind="out"):
        """Output, a line each; printed output keeps its blank lines and
        is folded later than a block's"""
        if kind == "printed":
            lines, fold = (text or "").split("\n"), 50
        else:
            lines, fold = [line for line in (text or "").splitlines() if line.strip()], FOLD
        if not lines:
            return
        shown = lines if len(lines) <= fold + 1 else lines[:fold]
        for line in shown:
            self.add(kind, line, depth=depth)
        if len(shown) < len(lines):
            self.add(kind, f"… {len(lines) - len(shown)} more lines", depth=depth,
                     more="\n".join(lines[len(shown):]))


class Kernel:
    """One script's env on this machine's UUTs, kept between commands.

    `root` is the workspace folder, `script` a path in it; `text`, if
    given, stands in for the script on disk (an editor's unsaved
    edits). `versions` maps a UUT to a version id (default: the newest
    each lists); `variation` is one of the script's, by name (default:
    the first, if it has any)."""

    def __init__(self, host, root, script, environment=None, versions=None,
                 variation=None, text=None, files_dir=None):
        self.host, self.root, self.script = host, Path(root), script
        self.text = text
        self.files_dir = Path(files_dir) if files_dir else None
        self.closure = self._resolve()
        found = self.closure
        if found.uuts and any(u not in host.uuts for u in found.uuts):
            missing = [u for u in found.uuts if u not in host.uuts]
            raise KernelError(f"No UUT plugin for {', '.join(missing)}")
        hosted = [e for e in (found.environments or host.environments)
                  if e in host.environments]
        if environment is None:
            if not hosted:
                raise KernelError(f"This machine hosts none of {script}'s environments "
                                  f"({', '.join(found.environments) or 'none declared'})")
            environment = hosted[0]
        if environment not in host.environments:
            raise KernelError(f"This machine doesn't host {environment}")
        if found.environments and environment not in found.environments:
            raise KernelError(f"{script} doesn't run in {environment}")
        self.environment = environment
        self.versions = {}
        for name in found.uuts:
            uut = host.uuts[name]
            wanted = (versions or {}).get(name)
            version = uut.find_version(wanted) if wanted else newest(uut)
            if version is None:
                raise KernelError(f"{name} has no version {wanted}" if wanted
                                  else f"{name} lists no versions")
            self.versions[name] = version
        names = [v.name for v in found.variations]
        if variation is not None and variation not in names:
            raise KernelError(f"{script} has no variation {variation}")
        self.variation = variation if variation is not None else (names[0] if names else None)

        self.env = None
        self.built = {}  # name -> value, as the env was built
        self.sources = {}  # name -> where it came from: a file, "uut" or "variation"
        self.clock = None
        self.held = {}  # the cleanups registered, kept across commands
        self.start = None  # "warm" or "fresh", once opened
        self.problem = None  # why the env couldn't be built, if it couldn't
        self.running = None  # the step running now, shown short
        self.current = None  # the Command running
        self.lines = []
        self.outcomes = {}  # command id -> its outcome, for the last commands
        self.counter = itertools.count(1)
        self.lines_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.used = time.monotonic()
        self.closed = False
        self.abandoned = 0
        self._start_thread()

    # The thread and its queue

    def _start_thread(self):
        self.queue = queue.Queue()
        self.generation = getattr(self, "generation", 0) + 1
        self.thread = threading.Thread(target=self._serve, args=(self.queue, self.generation),
                                       name="console-kernel", daemon=True)
        self.thread.start()

    def _serve(self, commands, generation):
        while True:
            command = commands.get()
            if command is None or generation != self.generation:
                return
            self.current = command
            self.stop_event.clear()
            try:
                self._do(command)
            except Exception:
                self.add_line(command, "error", traceback.format_exc().strip())
                command.outcome = "error"
            self.outcomes[command.id] = command.outcome or "pass"
            for old in list(self.outcomes)[:-MAX_OUTCOMES]:
                del self.outcomes[old]
            if generation != self.generation:
                return  # abandoned by a restart: a new thread carries on
            self.current, self.running = None, None

    def submit(self, kind, **details):
        if self.closed:
            raise KernelError("The console is closed")
        command = Command(kind, **details)
        self.used = time.monotonic()
        self.queue.put(command)
        return command

    def busy(self):
        return self.current is not None or not self.queue.empty()

    def wait_idle(self, timeout=None):
        """Wait until every command sent has run; True if they have"""
        end = None if timeout is None else time.monotonic() + timeout
        while self.busy():
            if end is not None and time.monotonic() > end:
                return False
            time.sleep(0.01)
        return True

    # What the page calls

    def open(self):
        return self.submit("open")

    def run_card(self, code, title=None, definitions=False, table=False, variations=()):
        """Run an rvt card's code as its block would run in the script"""
        return self.submit("card", code=code, title=title, definitions=definitions,
                           table=table, variations=list(variations))

    def run_forms(self, text, line=0, character=0, label=None, variations=(), table=None):
        """Run forms (typed, or a card's form at the cursor); `line` and
        `character` are where the text starts in its card, if it is from
        one, so a failure can point there. `table` is the code of the
        table card they are from, if they are: they run with its first
        row's symbols bound."""
        return self.submit("forms", text=text, line=line, character=character,
                           label=label, variations=list(variations), table=table)

    def reset(self, text=None):
        return self.submit("reset", text=text)

    def restart(self, text=None, abandon=False):
        """Reset, then start every UUT fresh. With `abandon`, a command
        that is still running after it is asked to stop is left behind on
        its thread, and a new one carries on."""
        if abandon and self.current is not None:
            self.stop()
            end = time.monotonic() + 2
            while self.current is not None and time.monotonic() < end:
                time.sleep(0.01)
            if self.current is not None:
                left = self.current
                self.abandoned += 1
                self.add_line(left, "note", "the command running didn't stop: it is "
                              "left running in the background")
                self.current, self.running = None, None
                self._start_thread()
        return self.submit("restart", text=text)

    def release(self):
        return self.submit("release")

    def stop(self):
        """Stop the command running at its next check, and drop the queued"""
        while True:
            try:
                dropped = self.queue.get_nowait()
            except queue.Empty:
                break
            if dropped is None:
                self.queue.put(None)  # closing: keep the end
                break
        self.stop_event.set()

    def close(self):
        """Stop, release what is held, and end the thread"""
        if self.closed:
            return
        self.stop()
        self.submit("release")
        self.queue.put(None)
        self.closed = True

    def clear(self):
        with self.lines_lock:
            self.lines = []

    def state(self):
        return {
            "script": self.script,
            "environment": self.environment,
            "versions": {name: v.id for name, v in self.versions.items()},
            "variation": self.variation,
            "variations": [v.name for v in self.closure.variations],
            "start": self.start,
            "problem": self.problem,
            "busy": self.busy(),
            "running": self.running,
            "queued": self.queue.qsize(),
            "held": [description for description, _ in self.held.values()],
            "abandoned": self.abandoned,
            "closed": self.closed,
            "last": self.lines[-1]["n"] if self.lines else 0,
            "outcomes": dict(self.outcomes),
        }

    def lines_since(self, n):
        with self.lines_lock:
            return [line for line in self.lines if line["n"] > n]

    def add_line(self, command, kind, text, **details):
        with self.lines_lock:
            self.lines.append({"n": next(self.counter), "command": command.id if command else None,
                               "kind": kind, "text": text, **details})
            del self.lines[:-MAX_LINES]

    def store_file(self, name, data):
        """Keep a file a block attached; returns the name it is kept as"""
        if self.files_dir is None:
            return None
        self.files_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(name).name).strip("-.") or "file"
        stored = f"{next(self.counter)}-{safe}"
        (self.files_dir / stored).write_bytes(data)
        return stored

    # Commands, on the kernel's thread

    def _do(self, command):
        kind = command.kind
        if kind == "open":
            self._start_uuts(fresh=False, command=command)
            self._build(command)
        elif kind == "reset":
            self._release(command)
            self._refresh(command.details.get("text"))
            self._build(command)
            self.add_line(command, "note", "reset")
        elif kind == "restart":
            self._release(command)
            self._refresh(command.details.get("text"))
            self._start_uuts(fresh=True, command=command)
            self._build(command)
        elif kind == "release":
            self._release(command, say_none=True)
        elif kind == "card":
            self._run_card(command)
        elif kind == "forms":
            self._run_forms(command)

    def _resolve(self):
        texts = {self.script: self.text} if self.text is not None else None
        try:
            return closures.resolve(self.root, self.script, texts=texts)
        except (OSError, ValueError) as e:
            raise KernelError(f"Can't read {self.script}: {e}") from e

    def _refresh(self, text):
        if text is not None:
            self.text = text
        self.closure = self._resolve()

    def _job(self):
        return {"environment": self.environment,
                "uut_versions": {name: {"id": v.id, "digest": v.digest}
                                 for name, v in self.versions.items()}}

    def _start_uuts(self, fresh, command):
        job = self._job()
        env = self.host.environments.get(self.environment)
        if not fresh and versions_installed(self.host, job):
            self.start = "warm"
            shown = ", ".join(f"{n} {v.id}" for n, v in self.versions.items())
            self.add_line(command, "note", f"attached to {shown or 'the environment'} "
                          f"as it is, in {self.environment}")
            return
        installed = install_uuts(self.host, job)
        for name, version in self.versions.items():
            self.host.uuts[name].start(version, env)
        self.start = "fresh"
        shown = ", ".join(f"{n} {v['id']} ({v['action']})" for n, v in installed.items())
        self.add_line(command, "note", f"started {shown or 'nothing'} fresh in "
                      f"{self.environment}")

    def _build(self, command):
        """The env, as a run builds it: the closure's definitions, the UUT
        handles and the variation's symbols"""
        found = self.closure
        try:
            env = executor.build_env(found.files, found.load_order, found.imports,
                                     self.variation)
            bound = handles(self.host, self._job())
            env.update({edn.Symbol(name): value for name, value in bound.items()})
            values = {}
            if self.variation is not None:
                values = executor.variation_values(
                    env, executor.find_variation(found.files[self.script], self.variation))
                env.update({edn.Symbol(s): v for s, v in values.items()})
            environment = self.host.environments.get(self.environment)
            self.clock = environment.clock(bound) if environment is not None else None
        except Exception as e:
            self.env, self.problem = None, f"{executor.error_line(e)}"
            self.add_line(command, "fail", f"Couldn't load {self.script}'s definitions: "
                          f"{self.problem}")
            return
        self.env, self.problem = env, None
        self.built = dict(dict.items(env))
        self.sources = self._sources(bound, values if self.variation is not None else {})
        if self.variation is not None:
            self.add_line(command, "note", f"variation {self.variation}")

    def _sources(self, bound, values):
        """name -> where it was defined: the file of each definition, "uut"
        for a UUT handle, "variation" for a variation's symbols"""
        found = {}
        for path in self.closure.load_order:
            try:
                statements = executor.read(self.closure.files[path], path)
            except ValueError:
                continue
            for statement in statements:
                if is_definition(statement.form) and len(statement.form) > 1:
                    found[str(statement.form[1])] = path
        found.update({name: "uut" for name in bound})
        found.update({str(name): "variation" for name in values})
        return found

    def names(self):
        """What the console's scope holds, beyond the language's own: each
        name with its kind, its value shown short, and where it came from
        ("console" for what was defined or changed since the env was
        built). Script and core.rst names first, in order of the files."""
        env = self.env
        if env is None:
            return []
        try:
            items = list(dict.items(env))
        except RuntimeError:  # changed while read: the kernel is running
            items = list(dict.items(dict(env)))
        order = {path: n for n, path in enumerate(self.closure.load_order)}
        order.update({"variation": -2, "uut": -3, "console": -1})
        found = []
        for name, value in items:
            name = str(name)
            source = self.sources.get(name, "console")
            if name not in self.built or self.built[name] is not value:
                source = "console"
            found.append({"name": name, "source": source, **described(value, source)})
        found.sort(key=lambda n: (order.get(n["source"], len(order)), n["name"]))
        return found

    def _release(self, command, say_none=False):
        if not self.held:
            if say_none:
                self.add_line(command, "note", "nothing is held")
            return
        observer = _Released(self, command)
        count = len(self.held)
        with clocks.keeping(self.clock), context.stopping(None):
            executor.run_cleanups(self.held, observer)
        self.add_line(command, "note", f"released {count} held value{'s' * (count != 1)}")

    def _ready(self, command):
        if self.env is None:
            self.add_line(command, "fail", self.problem or "The console isn't open")
            command.outcome = "error"
            return False
        return True

    def _limited(self, command, variations):
        """True (and say so) if what runs is limited to other variations.
        `variations` is the names it is for, or a list of such lists (a
        card's own, and the variant sections it is in): each must allow
        the console's."""
        scopes = [s for s in (variations or ()) if s]
        if scopes and all(isinstance(s, str) for s in scopes):
            scopes = [scopes]
        for names in scopes:
            names = [v for v in names if v]
            if names and self.variation not in names:
                self.add_line(command, "fail", f"This is for {', '.join(names)}; the console "
                              f"runs {self.variation or 'no variation'}.")
                command.outcome = "skipped"
                return True
        return False

    def _running(self):
        """The contexts a command runs in: the kernel's env, its held
        cleanups, its clock and its stop"""
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(context.running(self.env))
        stack.enter_context(context.cleanups(self.held))
        stack.enter_context(clocks.keeping(self.clock))
        stack.enter_context(context.stopping(self.stop_event))
        return stack

    def _run_card(self, command):
        d = command.details
        title = d.get("title")
        self.add_line(command, "command", f"▶ {short(title or label(d['code']) or '(empty)')}")
        if not self._ready(command) or self._limited(command, d.get("variations", ())):
            return
        from ...framework.cards import RVT, Card, rvt_source
        code = d["code"]
        text = rvt_source(Card(RVT, title=title, definitions=bool(d.get("definitions")),
                               table=bool(d.get("table")), code=code))
        # The file line (1-based) of the card's first line of code: rvt_source
        # drops leading blank lines
        blank = len(code) - len(code.lstrip("\n"))
        first = text.split("\n\n", 1)[0].count("\n") + 3
        try:
            statements = executor.read(text, CARD)
        except ValueError as e:
            self.add_line(command, "fail", str(e))
            command.outcome = "error"
            return

        def place(span):
            if span.get("source") != CARD:
                return None
            return {"line": span["line"] - first + blank,
                    "character": max(0, span["col"] - len("   "))}

        self._run(command, statements, place)

    def _run_forms(self, command):
        d = command.details
        label = d.get("label") or d["text"]
        self.add_line(command, "command", f"» {short(label)}")
        if not self._ready(command) or self._limited(command, d.get("variations", ())):
            return
        try:
            forms = [form for form, _ in edn.read_all_with_spans(d["text"])]
        except edn.ParseError as e:
            self.add_line(command, "fail", str(e))
            command.outcome = "error"
            return
        line0, char0 = d.get("line") or 0, d.get("character") or 0

        def place(span):
            if span.get("source") is not None:
                return None
            return {"line": span["line"] + line0,
                    "character": span["col"] + (char0 if span["line"] == 0 else 0)}

        transcript = Transcript(self, command, place)
        observer = transcript
        outcome = "pass"
        env = self._row_env(command, d.get("table"))
        if env is None:
            return
        with self._running():
            for index, form in enumerate(forms):
                if is_definition(form):
                    if not executor.define(form, env, observer, index):
                        outcome = "error"
                        break
                    self.add_line(command, "result", f"=> #'{form[1]}")
                elif is_step(form) or not isinstance(form, list):
                    result = executor.run_step(form, env, observer, index)
                    if not result:
                        outcome = "error" if result.error else "fail"
                        break
                    self.add_line(command, "result",
                                  f"=> {short(edn.writes(result.value), 400)}")
                else:
                    self.add_line(command, "note", f"{short(edn.writes(form), 60)} is a "
                                  "declaration: the console takes the script's")
        command.outcome = outcome
        self._said_stopped(command)

    def _row_env(self, command, table):
        """The env forms from a table card run in: the kernel's, with the
        table's first row bound; None (and why) if the rows can't be read"""
        if not table:
            return self.env
        from ...framework import lisp
        from ...framework.language import parse_table
        try:
            first = edn.read_all_with_spans(table)[0][0]
        except (edn.ParseError, IndexError) as e:
            self.add_line(command, "fail", f"Can't read the table's rows: {e}")
            command.outcome = "error"
            return None
        errors = []
        rows = parse_table(CARD, first, errors)
        if errors or not rows:
            self.add_line(command, "fail", errors[0] if errors else "The table has no rows")
            command.outcome = "error"
            return None
        row, env = rows[0], lisp.Env(outer=self.env)
        try:
            with self._running():
                for symbol, value in zip(row.symbols, row.forms):
                    env[edn.Symbol(symbol)] = lisp.eval(value, self.env)
        except Exception as e:
            self.add_line(command, "fail", f"row {row.name}: {executor.error_line(e)}")
            command.outcome = "error"
            return None
        self.add_line(command, "row", f"with row {row.name}")
        return env

    def _run(self, command, statements, place):
        transcript = Transcript(self, command, place)
        observer = transcript
        with self._running():
            outcome, placeholders = executor.run_statements(
                statements, observer, CARD, self.env, variation=self.variation,
                redefine=True)
        if outcome == "pass" and placeholders:
            outcome = "incomplete"
        command.outcome = outcome
        ran = [s for s in statements if s.applies(self.variation)
               and (is_step(s.form) or is_definition(s.form))]
        if outcome == "pass" and ran and all(is_definition(s.form) for s in ran):
            names = ", ".join(str(s.form[1]) for s in ran)
            self.add_line(command, "result", f"defined {short(names, 80)}")
        elif outcome in ("blocked", "released"):
            self.add_line(command, "fail", "the precondition doesn't hold")
        self._said_stopped(command)

    def _said_stopped(self, command):
        if self.stop_event.is_set():
            self.add_line(command, "note", "stopped")


class _Released:
    """Reports the console's cleanups as transcript lines"""

    def __init__(self, kernel, command):
        self.kernel, self.command = kernel, command

    def on_cleanup(self, description, passed, message="", **kw):
        if not passed:
            self.kernel.add_line(self.command, "fail", f"{description}: {message}")
        else:
            self.kernel.add_line(self.command, "ref", description)


def find_form(code, line, character):
    """The top-level form of `code` the cursor (0-based line and
    character) is in or just after: (its text, its line, its
    character), or None"""
    try:
        found = edn.read_all_with_spans(code, readable=True)
    except edn.ParseError:
        return None
    lines = code.split("\n")

    def offset(at_line, at_char):
        return sum(len(text) + 1 for text in lines[:at_line]) + at_char

    cursor = offset(line, character)
    best = None
    for form, span in found:
        if span is None:
            continue
        start, end = offset(span.line, span.col), offset(span.end_line, span.end_col)
        if start <= cursor <= end:
            best = span
            break
        if end <= cursor:
            best = span  # the last form before the cursor
    if best is None:
        return None
    start, end = offset(best.line, best.col), offset(best.end_line, best.end_col)
    return code[start:end], best.line, best.col
