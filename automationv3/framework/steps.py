"""Running a script's steps, and the blocks called inside them

Each top-level statement of a script is a step. Blocks can be called
anywhere inside one (top level, defn, let, if, ...), and every call
runs and reports the same way wherever it is: a call that fails (an
assertion that comes out false, or a block that raises) stops the
step right there. A defn is transparent: the blocks it calls report as
calls of the step that called it.

Only blocks fail steps. A step passes unless a block call in it failed
or something raised; the value it comes to is shown, never judged. To
check a value, assert it: (Verify (fuel-level-ok? 40)).

Three forms change that, explicitly:

- (step "title" body...) groups its block calls under one reported
  entry, with the title. A failure inside still stops it, and the step
  around it.
- (try-ok? form) runs the form and gives true if no block call in it
  failed, false if one did, without stopping the step. Calls in it are
  reported as suppressed.
- (try form default) does the same but gives the form's value, or
  `default` (evaluated) if a block call failed.

try-ok? and try catch block failures only: a script's own mistakes (an
unknown name, a bad call) still stop the step.

(quietly forms...) runs forms with their calls left out of the output.

Every reported block call gets an id within its statement, its parent
(an enclosing step form) if any, a depth, its block_kind, and its quiet /
suppressed flags; in a precondition, also the phase (check or heal) it
was made in.
"""

import contextvars
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, replace

from . import context, edn, lisp
from .block import ASSERTION, VALUE, BlockResult, block_names, find_block


class StepFailed(Exception):
    """A block call failed, which stops the step (unless caught by
    try-ok? or try)"""

    def __init__(self, form, result):
        super().__init__(f"{form} failed")
        self.form = form
        self.result = result


class RemovedForm(Exception):
    """A form the language no longer has"""


@dataclass(frozen=True)
class Frame:
    quiet: bool = False
    suppressed: bool = False  # inside try-ok? / try
    parent: int = None  # the enclosing step form's call
    depth: int = 0


class Runtime:
    """Reports and runs the block calls of one statement"""

    def __init__(self, observer, index):
        self.observer = observer
        self.index = index
        self.calls = 0
        self.frames = [Frame()]
        self.phase = None  # the precondition phase running, numbered from 1

    @property
    def frame(self):
        return self.frames[-1]

    @contextmanager
    def within(self, **changes):
        self.frames.append(replace(self.frame, **changes))
        try:
            yield self.frame
        finally:
            self.frames.pop()

    def call(self, form, run, kind=None, title=None):
        """Report and run one call (a block's, or a step form's). `run(call_id)`
        returns a BlockResult. Raises StepFailed if it fails; a failure
        or error raised inside a step form is reported against it and
        raised on."""
        frame = self.frame
        self.calls += 1
        call = self.calls
        details = dict(index=self.index, call=call, parent=frame.parent,
                       depth=frame.depth, quiet=frame.quiet,
                       suppressed=frame.suppressed, block_kind=kind)
        if title is not None:
            details["title"] = title
        if self.phase is not None:
            details["phase"] = self.phase
        self.observer.on_call_start(form=form, **details)
        started = time.monotonic()
        try:
            result = run(call)
        except StepFailed as failed:
            self.end(details, started, BlockResult(
                False, stderr=f"{failed.form} failed", error=failed.result.error))
            raise
        except Exception as e:
            self.end(details, started, BlockResult(False, stderr=error_line(e),
                                                   error=True))
            raise
        self.end(details, started, result, kind)
        if not result:
            raise StepFailed(form, result)
        return result

    def end(self, details, started, result, kind=None):
        extra = {}
        if kind == VALUE and result:
            extra["value"] = text(result.value)
        self.observer.on_call_end(
            passed=bool(result), error=result.error, stdout=result.stdout,
            stderr=result.stderr, duration=elapsed(started), **extra, **details)


def error_line(e):
    """A one-line description of an exception"""
    return f"{type(e).__name__}: {e}"


def attach(name, data):
    """Attach a file (bytes or text) to the running step's run. Observers
    store it; on a report it is listed with the step."""
    runtime = current_runtime()
    if isinstance(data, str):
        data = data.encode()
    runtime.observer.on_attach(index=runtime.index, name=name, data=data)


def elapsed(started):
    """Seconds since `started` (a time.monotonic()), to the millisecond"""
    return round(time.monotonic() - started, 3)


_runtime = contextvars.ContextVar("runtime", default=None)


@contextmanager
def running_statement(runtime):
    token = _runtime.set(runtime)
    try:
        yield runtime
    finally:
        _runtime.reset(token)


def current_runtime():
    runtime = _runtime.get()
    if runtime is None:
        raise RuntimeError("Blocks can only run as part of a script")
    return runtime


def as_result(value):
    """A value as a BlockResult: passing if truthy"""
    if isinstance(value, BlockResult):
        return value
    return BlockResult(bool(value), value=value)


def text(form):
    return edn.writes(form)


def run_block(block, env):
    """Execute a found block, always returning a BlockResult (an error
    one if it raised).

    `env` is the call site's environment (e.g. inside a defn, with its
    parameters bound); the block's arguments are evaluated in it.
    """
    try:
        with context.running(env):
            return block.execute(env)
    except Exception as e:
        result = BlockResult(False, stderr=traceback.format_exc(), error=True)
        result.exception = e
        return result


def call_value(block, result):
    """What a block call gives the code around it"""
    if block.block.kind == ASSERTION:
        return bool(result.passed)
    return result.value


# Blocks as Lisp special forms: a call reports through the runtime


def is_block_name(symbol):
    return isinstance(symbol, edn.Symbol) and str(symbol) in block_names()


@lisp.special_form(is_block_name)
def block_special_form(x, env):
    if x[0] in env:  # a script definition shadows the block
        proc = env[x[0]]
        return proc(*[lisp.eval(arg, env) for arg in x[1:]])
    block = find_block(x)
    if block is None:
        raise ValueError(f"No form of {x[0]} matches {text(x)}: "
                         f"see its usage, {usage_of(x[0])}")
    result = current_runtime().call(text(x), lambda call: run_block(block, env),
                                    kind=block.block.kind)
    return call_value(block, result)


def usage_of(name):
    from .block import all_blocks
    for block in all_blocks():
        if block.name() == name:
            return " or ".join(block.usage().splitlines())
    return name


@lisp.special_form("step")
def step_special_form(x, env):
    """(step "title" body...): the body's block calls reported under one
    entry with the title; gives the body's value"""
    if len(x) < 2 or not isinstance(x[1], str) or isinstance(x[1], edn.Symbol):
        raise SyntaxError('step takes a title string, then its body: (step "title" ...)')
    title, body = x[1], x[2:]
    runtime = current_runtime()

    def run(call):
        with runtime.within(parent=call, depth=runtime.frame.depth + 1,
                            suppressed=False):
            value = None
            for form in body:
                value = lisp.eval(form, env)
        return BlockResult(True, value=value)

    return runtime.call(title, run, kind="step", title=title).value


@lisp.special_form("try-ok?")
def try_ok_special_form(x, env):
    """(try-ok? form): true if no block call in it failed, else false"""
    if len(x) != 2:
        raise SyntaxError("try-ok? takes one form: (try-ok? form)")
    with current_runtime().within(suppressed=True):
        try:
            lisp.eval(x[1], env)
            return True
        except StepFailed:
            return False


@lisp.special_form("try")
def try_special_form(x, env):
    """(try form default): the form's value, or default's if a block call
    in it failed"""
    if len(x) != 3:
        raise SyntaxError("try takes a form and a default: (try form default)")
    with current_runtime().within(suppressed=True):
        try:
            return lisp.eval(x[1], env)
        except StepFailed:
            pass
    return lisp.eval(x[2], env)


@lisp.special_form("quietly")
def quietly_special_form(x, env):
    """(quietly forms...): run forms with their block calls left out of
    the output"""
    value = None
    with current_runtime().within(quiet=True):
        for form in x[1:]:
            value = lisp.eval(form, env)
    return value


REMOVED = {
    "defblock": "defblock was removed: use defn. A failing block now stops "
                "wherever it is called; group calls with (step \"title\" ...) "
                "and suppress failures explicitly with try-ok? or try",
    "passes?": "passes? was renamed try-ok?",
}


def removed_form(x, env):
    raise RemovedForm(REMOVED[str(x[0])])


for _name in REMOVED:
    lisp.special_form(_name)(removed_form)


# Statements


def run_statement(form, env, runtime):
    """Run one top-level step form, always returning a BlockResult.

    A block written directly as the statement is the step itself. Any
    other form is evaluated: its block calls report through `runtime`,
    and it passes unless one of them failed or it raised. The result's
    value is what the form came to.
    """
    name = form[0] if form else None
    try:
        if is_block_name(name) and name not in env:
            block = find_block(form)
            if block is None:
                return BlockResult(False, error=True,
                                   stderr=f"No form of {name} matches {text(form)}: "
                                          f"see its usage, {usage_of(name)}")
            result = run_block(block, env)
            if result:
                result.value = call_value(block, result)
            return result

        if (isinstance(name, edn.Symbol) and name not in env
                and not lisp.get_special_form(name)):
            return BlockResult(
                False, error=True,
                stderr=f"No BuildingBlock or definition matches {text(form)}")

        try:
            value = lisp.eval(form, env)
        except StepFailed as failed:
            stderr = f"{failed.form} failed\n{failed.result.stderr}".strip()
            return BlockResult(False, stdout=failed.result.stdout, stderr=stderr,
                               error=failed.result.error)
        stdout = f"returned {text(value)}" if value is not None else ""
        return BlockResult(True, stdout=stdout, value=value)
    except Exception as e:
        result = BlockResult(False, stderr=traceback.format_exc(), error=True)
        result.exception = e
        return result
