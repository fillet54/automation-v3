"""Executes scripts, reporting progress to an observer

A script is an rst document (see document.py). Its statements are its
parts: prose chunks are reported as comments as the run reaches them,
and each form of its rvt blocks is a statement. Directives (import, uut,
environments, variations) are skipped; every other form is a step. Statement indexes
match `statements.get_statements`, so a report can line results up with
the rendered script.

Definitions (def, defn, defblock) are not steps. A script's definitions
section is loaded before anything runs, along with its core.rst files;
a definition elsewhere runs where it is, without being reported unless
it fails.

A step is run by `steps.run_statement`: a block written as the statement
is the step; anything else (a defn call, an if, ...) is evaluated as
Lisp, with the blocks it calls reported as calls of that step. See
steps.py for how composed blocks report and fail.

Blocks limited to other variations (`:variations:`, see document.py)
are skipped without being reported: their steps don't run and their
definitions aren't loaded.

The first failing step stops the script: the outcome is "fail" and
later statements are not reported.

Preconditions run like steps: the check, then (if it failed and there
is one) the heal and the check again. A precondition that still fails
ends the script before its steps. In "probe" mode the outcome is then
"released": the worker gives the job back because this environment
isn't ready for it. In any other mode the outcome is "blocked".
"""

import time
import traceback

from . import context, document, edn, lisp
from .block import BlockResult
from .closure import (
    DEFINITIONS,
    DIRECTIVES,
    PRECONDITION,
    head,
    is_definition,
    parse_precondition,
    parse_variations,
)
from .steps import Runtime, run_statement, running_statement


def is_comment(form):
    return isinstance(form, str) and not isinstance(form, (edn.Symbol, edn.Keyword))


def new_env():
    return lisp.Env(outer=lisp.global_env)


def run_precondition(form, env, runtime):
    """Check, heal if needed, check again. Returns a BlockResult."""
    parsed = parse_precondition(form)
    if parsed is None:
        return BlockResult(False, stderr="Malformed Precondition")
    _, check, heal = parsed
    result = run_statement(check, env, runtime)
    if result or heal is None:
        return result
    healed = run_statement(heal, env, runtime)
    if healed.stderr:  # the heal itself raised or had no block
        return BlockResult(False, stdout=result.stdout, stderr=healed.stderr)
    result = run_statement(check, env, runtime)
    return BlockResult(bool(result), stdout=f"healed; {result.stdout}".strip("; "),
                       stderr=result.stderr)


def load_definitions(env, text, keep=frozenset()):
    """Evaluate the definitions (def, defn, defblock) of a core.rst into `env`.

    Names in `keep` are already defined and are not overridden.
    """
    for form in document.forms(text):
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

    Returns "pass", "fail", "blocked", or (in probe mode) "released".
    """
    env = env if env is not None else new_env()
    with context.running(env):
        return _execute(text, observer, script, env, mode, variation)


def _execute(text, observer, script, env, mode, variation):
    parts = document.parse(text)
    forms = [part.form for part in parts]
    observer.on_procedure_begin(script=script, statements=len(forms), mode=mode)
    section = set(document.definitions_section(parts))

    outcome = "pass"
    for index, form in enumerate(forms):
        if not parts[index].applies(variation):
            continue
        if is_comment(form):
            observer.on_comment(index=index, text=form)
        elif is_definition(form):
            if index in section and dict.__contains__(env, form[1]):
                continue  # loaded with the closure
            result = define(form, env)
            if not result:
                observer.on_step_start(index=index, form=edn.writes(form).strip(),
                                       definition=True)
                observer.on_step_end(index=index, passed=False, stdout="",
                                     stderr=result.stderr, duration=0,
                                     definition=True)
                outcome = "fail"
                break
        elif isinstance(form, list) and head(form) not in DIRECTIVES:
            precondition = head(form) == PRECONDITION
            observer.on_step_start(
                index=index, form=edn.writes(form).strip(), precondition=precondition
            )
            started = time.monotonic()
            run = run_precondition if precondition else run_statement
            runtime = Runtime(observer, index)
            with running_statement(runtime):
                result = run(form, env, runtime)
            observer.on_step_end(
                index=index,
                passed=bool(result),
                stdout=result.stdout,
                stderr=result.stderr,
                duration=round(time.monotonic() - started, 3),
                precondition=precondition,
            )
            if not result:
                if not precondition:
                    outcome = "fail"
                elif mode == "probe":
                    outcome = "released"
                else:
                    outcome = "blocked"
                break

    observer.on_procedure_end(outcome=outcome)
    return outcome


def define(form, env):
    """Evaluate a definition, returning a BlockResult"""
    try:
        lisp.eval(form, env)
        return BlockResult(True)
    except Exception:
        return BlockResult(False, stderr=traceback.format_exc())


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
            load_definitions(env, files[path], keep=chain_names)
        else:
            load_definitions(env, files[path])
            chain_names = set(env)
    load_script_definitions(env, document.parse(files[load_order[-1]]), variation)
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
