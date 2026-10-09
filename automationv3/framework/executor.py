"""Executes scripts, reporting progress to an observer

A script is an rst document (see document.py). Its statements are its
parts: prose chunks are reported as comments as the run reaches them,
and each form of its rvt blocks is a statement. Directives (import, uut,
environments, variations) are skipped; every other form is a step. Statement indexes
match `statements.get_statements`, so a report can line results up with
the rendered script.

Definitions (def, defn) are not steps. A script's definitions
section is loaded before anything runs, along with its core.rst files;
a definition elsewhere runs where it is, without being reported unless
it fails.

A step is run by `steps.run_statement`: a block written as the statement
is the step; anything else (a defn call, an if, ...) is evaluated as
Lisp, with the blocks it calls reported as calls of that step. Only
block calls fail a step; see steps.py for how they report and fail.

Blocks limited to other variations (`:variations:`, see document.py)
are skipped without being reported: their steps don't run and their
definitions aren't loaded.

The first failing step stops the script and later statements are not
reported. The outcome is "fail" if an assertion came out false, and
"error" if something raised: a block, or the script's own code (an
unknown name, a definition that couldn't be evaluated).

Preconditions run like steps: the check, then (if it failed and there
is one) the heal and the check again. A check holds only if nothing in
it failed and its value is truthy. Each of these is reported as a
phase of the precondition's step (phase_start / phase_end, with the
block calls it makes tagged with its phase), so pages can show a
precondition like a titled block. A precondition that still fails
ends the script before its steps. In "probe" mode the outcome is then
"released": the worker gives the job back because this environment
isn't ready for it. In any other mode the outcome is "blocked".
"""

import time
import traceback

from . import context, document, edn, lisp
from .block import BlockResult
from .language import (
    DEFINITIONS,
    PRECONDITION,
    head,
    is_definition,
    is_step,
    parse_precondition,
    parse_variations,
)
from .steps import Runtime, elapsed, error_line, run_statement, running_statement


def new_env():
    return lisp.Env(outer=lisp.global_env)


def run_phase(action, form, env, runtime):
    """Run one phase (a check or the heal) of a precondition, reported as
    such. Returns a BlockResult. A check passes only if its value is
    truthy too."""
    runtime.phase = (runtime.phase or 0) + 1
    details = dict(index=runtime.index, phase=runtime.phase, action=action)
    runtime.observer.on_phase_start(form=edn.writes(form), **details)
    started = time.monotonic()
    result = run_statement(form, env, runtime)
    if action == "check" and result and not result.value:
        result.passed = False
        result.message = f"{edn.writes(form)} came out {edn.writes(result.value)}"
        span = edn.span_of(form)
        result.trace = [span._asdict()] if span else []
    runtime.observer.on_phase_end(passed=bool(result), error=result.error,
                                  **failure_details(result), stdout=result.stdout,
                                  stderr=result.stderr, duration=elapsed(started),
                                  **details)
    return result


def run_precondition(form, env, runtime):
    """Check, heal if needed, check again. Returns a BlockResult."""
    parsed = parse_precondition(form)
    if parsed is None:
        result = BlockResult(False, stderr="Malformed Precondition")
        result.message, result.trace = "Malformed Precondition", []
        return result
    check, heal = parsed.check, parsed.heal
    result = run_phase("check", check, env, runtime)
    if result or heal is None:
        return result
    healed = run_phase("heal", heal, env, runtime)
    if not healed:  # the heal itself failed
        healed.stdout = result.stdout
        return healed
    result = run_phase("check", check, env, runtime)
    result.stdout = f"healed; {result.stdout}".strip("; ")
    return result


def load_definitions(env, text, keep=frozenset(), path=None):
    """Evaluate the definitions (def, defn) of a core.rst into `env`.

    Names in `keep` are already defined and are not overridden.
    """
    for form in document.forms(text, path=path):
        if head(form) in DEFINITIONS and form[1] not in keep:
            lisp.eval(form, env)


def load_script_definitions(env, parts, variation=None):
    """Evaluate the script's definitions section into `env`, leaving out
    blocks limited to other variations"""
    for index in document.definitions_section(parts):
        if is_definition(parts[index].form) and parts[index].applies(variation):
            lisp.eval(parts[index].form, env)


def execute_script(text, observer, script=None, env=None, mode="normal",
                   variation=None):
    """Run the statements of `text` in order, as `variation` (a name) if
    given.

    Returns "pass", "fail", "error", "blocked", or (in probe mode)
    "released".
    """
    env = env if env is not None else new_env()
    with context.running(env):
        return _execute(text, observer, script, env, mode, variation)


def _execute(text, observer, script, env, mode, variation):
    parts = document.parse(text, path=script)
    observer.on_procedure_begin(script=script, statements=len(parts), mode=mode)
    preloaded = set(document.definitions_section(parts))

    outcome = "pass"
    for index, part in enumerate(parts):
        form = part.form
        if not part.applies(variation):
            continue
        if part.prose:
            observer.on_comment(index=index, text=form)
        elif is_definition(form):
            if index in preloaded and dict.__contains__(env, form[1]):
                continue  # loaded with the closure
            if not _define(form, env, observer, index):
                outcome = "error"
                break
        elif is_step(form):
            result = _run_step(form, env, observer, index)
            if not result:
                if head(form) == PRECONDITION:
                    outcome = "released" if mode == "probe" else "blocked"
                else:
                    outcome = "error" if result.error else "fail"
                break

    observer.on_procedure_end(outcome=outcome)
    return outcome


def failure_details(result):
    """What a failed step's report says about why and where"""
    if result:
        return {}
    return {"message": getattr(result, "message", "") or "",
            "trace": getattr(result, "trace", None) or []}


def _define(form, env, observer, index):
    """Evaluate a definition where it is in the script; only a failure is
    reported (as a step). Returns whether it succeeded."""
    try:
        lisp.eval(form, env)
        return True
    except Exception as e:
        details = dict(index=index, definition=True)
        trace = lisp.trace(e) or [edn.span_of(form)]
        observer.on_step_start(form=edn.writes(form), **details)
        observer.on_step_end(passed=False, error=True, stdout="",
                             stderr=traceback.format_exc(), duration=0,
                             message=error_line(e),
                             trace=[span._asdict() for span in trace if span], **details)
        return False


def _run_step(form, env, observer, index):
    """Run and report one step (or Precondition). Returns its BlockResult."""
    precondition = head(form) == PRECONDITION
    details = dict(index=index, precondition=precondition)
    observer.on_step_start(form=edn.writes(form), **details)
    started = time.monotonic()
    runtime = Runtime(observer, index)
    run = run_precondition if precondition else run_statement
    with running_statement(runtime):
        result = run(form, env, runtime)
    observer.on_step_end(passed=bool(result), error=result.error,
                         stdout=result.stdout, stderr=result.stderr,
                         duration=elapsed(started), **failure_details(result),
                         **details)
    return result


def build_env(files, load_order, imports=(), variation=None):
    """An env holding the definitions of every core.rst in the closure,
    then the script's definitions section (as `variation`, if given).

    Files in `imports` only add definitions: they never override a name
    defined by the script's own core.rst chain. Only definition forms
    are evaluated, so building it never runs a step.
    """
    env = new_env()
    chain_names = set()
    for path in load_order[:-1]:
        if path in imports:
            load_definitions(env, files[path], keep=chain_names, path=path)
        else:
            load_definitions(env, files[path], path=path)
            chain_names = set(env)
    script = load_order[-1]
    load_script_definitions(env, document.parse(files[script], path=script), variation)
    return env


def variation_values(env, variation):
    """symbol -> value for a Variation, evaluated in `env`"""
    return {
        symbol: lisp.eval(form, env)
        for symbol, form in zip(variation.symbols, variation.forms)
    }


def find_variation(text, name):
    for form in document.forms(text):
        if head(form) == "variations":
            errors = []
            for variation in parse_variations("", form, errors):
                if variation.name == name:
                    return variation
    raise ValueError(f"No variation named {name}")


def execute_closure(files, load_order, observer, imports=(), variation=None,
                    bindings=None, mode="normal"):
    """Load the core.rst files in order, then run the script (last).

    With `variation` (a name), that variation's symbols are bound before
    the script runs. `bindings` (name -> value) are bound too, e.g. the
    handles scripts use to reach their UUTs.
    """
    env = build_env(files, load_order, imports, variation)
    env.update({edn.Symbol(name): value for name, value in (bindings or {}).items()})
    script = load_order[-1]
    if variation is not None:
        values = variation_values(env, find_variation(files[script], variation))
        env.update({edn.Symbol(symbol): value for symbol, value in values.items()})
    return execute_script(files[script], observer, script=script, env=env, mode=mode,
                          variation=variation)
