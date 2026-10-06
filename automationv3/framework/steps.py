"""Running a script's steps, and blocks composed inside them

Each top-level statement of a script is a step. Blocks can be called
anywhere inside one (top level, defn, let, if, ...), and where the call
happens decides how it reports and fails:

- At the top level or in a plain defn, a block call acts as a top-level
  step: it is reported as its own result, and a failure stops the
  statement (and so the script) right there.
- Inside a defblock, block calls are nested under the defblock's call
  and their failures don't stop it; the defblock passes on the
  truthiness of what it returns (or the BlockResult it returns).
- Inside (quietly ...), calls run and fail as usual but observers are
  told they are quiet, so they are left out of the output.
- (passes? expr) evaluates expr without letting block failures stop the
  step, and returns true or false.

Every reported block call gets an id within its statement, its parent
call (a defblock) if any, a depth, and its quiet / checked flags; in a
precondition, also the phase (check or heal) it was made in.
"""

import contextvars
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, replace

from . import context, edn, lisp
from .block import BlockResult, block_names, find_block


class StepFailed(Exception):
    """A block call failed where failures stop the step"""

    def __init__(self, form, result):
        super().__init__(f"{form} failed")
        self.form = form
        self.result = result


@dataclass(frozen=True)
class Frame:
    nested: bool = False  # inside a defblock: failures don't stop
    quiet: bool = False
    checking: bool = False  # inside passes?: failures don't stop
    parent: int = None  # the enclosing defblock call
    depth: int = 0

    @property
    def stops_on_failure(self):
        return not (self.nested or self.checking)


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

    def call(self, form, run):
        """Report and run one block call. `run(call_id)` returns a
        BlockResult. Raises StepFailed if it fails where that stops the
        step; otherwise returns the result."""
        frame = self.frame
        self.calls += 1
        call = self.calls
        details = dict(index=self.index, call=call, parent=frame.parent,
                       depth=frame.depth, quiet=frame.quiet, checked=frame.checking)
        if self.phase is not None:
            details["phase"] = self.phase
        self.observer.on_call_start(form=form, **details)
        started = time.monotonic()
        try:
            result = as_result(run(call))
        except StepFailed:
            raise
        except Exception:
            result = BlockResult(False, stderr=traceback.format_exc())
        self.observer.on_call_end(
            passed=bool(result), stdout=result.stdout, stderr=result.stderr,
            duration=elapsed(started), **details)
        if not result and frame.stops_on_failure:
            raise StepFailed(form, result)
        return result


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
    """A block's or step's value as a BlockResult: passing if truthy"""
    if isinstance(value, BlockResult):
        return value
    return BlockResult(bool(value))


def returned(value):
    """A form's value as a BlockResult that says what it returned"""
    if isinstance(value, BlockResult):
        return value
    return BlockResult(bool(value), stdout=f"returned {text(value)}")


def text(form):
    return edn.writes(form)


def run_block(block, env):
    """Execute a found block, always returning a BlockResult.

    `env` is the call site's environment (e.g. inside a defn, with its
    parameters bound); blocks that evaluate their own forms use it.
    """
    try:
        with context.running(env):
            return as_result(block.execute(env))
    except Exception:
        return BlockResult(False, stderr=traceback.format_exc())


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
        raise ValueError(f"No BuildingBlock matches {text(x)}")
    return current_runtime().call(text(x), lambda call: run_block(block, env))


class DefBlock:
    """A block defined in a script with defblock"""

    def __init__(self, name, fn):
        self.name = name
        self.fn = fn

    def run(self, runtime, call, args):
        """Run the body with its block calls nested under `call`"""
        with runtime.within(nested=True, parent=call, depth=runtime.frame.depth + 1):
            return returned(self.fn(*args))

    def __call__(self, *args):
        runtime = current_runtime()
        form = text(edn.List([edn.Symbol(self.name), *args]))
        return runtime.call(form, lambda call: self.run(runtime, call, args))


@lisp.special_form("defblock")
def defblock_special_form(x, env):
    """(defblock name [params] body...)"""
    _, name, params, *body = x
    fn = lisp.eval(edn.List([edn.Symbol("fn"), params, *body]), env)
    env[name] = DefBlock(str(name), fn)
    return env[name]


@lisp.special_form("passes?")
def passes_special_form(x, env):
    """(passes? expr): true or false, never stopping the step"""
    with current_runtime().within(checking=True):
        return bool(lisp.eval(x[1], env))


@lisp.special_form("quietly")
def quietly_special_form(x, env):
    """(quietly forms...): run forms with their block calls left out of
    the output"""
    value = None
    with current_runtime().within(quiet=True):
        for form in x[1:]:
            value = lisp.eval(form, env)
    return value


# Statements


def run_statement(form, env, runtime):
    """Run one top-level step form, always returning a BlockResult.

    A block written directly as the statement is the step itself. Any
    other form is evaluated: its block calls report through `runtime`,
    and it passes if no call stopped it and its value is truthy.
    """
    name = form[0] if form else None
    try:
        if is_block_name(name) and name not in env:
            block = find_block(form)
            if block is None:
                return BlockResult(
                    False, stderr=f"No BuildingBlock matches {text(form)}")
            return run_block(block, env)

        defined = isinstance(name, edn.Symbol) and name in env
        if defined and isinstance(env[name], DefBlock):
            args = [lisp.eval(arg, env) for arg in form[1:]]
            return env[name].run(runtime, None, args)

        if (isinstance(name, edn.Symbol) and not defined
                and not lisp.get_special_form(name)):
            return BlockResult(
                False, stderr=f"No BuildingBlock or definition matches {text(form)}")

        try:
            value = lisp.eval(form, env)
        except StepFailed as failed:
            stderr = f"{failed.form} failed\n{failed.result.stderr}".strip()
            return BlockResult(False, stdout=failed.result.stdout, stderr=stderr)
        return returned(value)
    except Exception:
        return BlockResult(False, stderr=traceback.format_exc())
