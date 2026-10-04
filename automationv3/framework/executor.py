"""Executes edn test scripts, reporting progress to an observer

Each top-level form is a statement. Plain strings are documentation and
are reported as comments; directives (import, uut, environments) are
skipped; every other list is a step. Statement indexes match
`testcase.get_statements`, so a report can line results up with the
rendered script.

A step whose head is a function defined (with defn) in the script's
core.rvt files is called with Lisp-evaluated arguments and passes if it
returns something truthy. Any other step runs through its BuildingBlock,
which receives its arguments unevaluated.

The first failing step stops the script: the outcome is "fail" and
later statements are not reported.
"""

import time
import traceback

from . import edn, lisp
from .block import BlockResult, find_block
from .closure import DEFINITIONS, DIRECTIVES, head, parse_variations


def is_comment(form):
    return isinstance(form, str) and not isinstance(form, (edn.Symbol, edn.Keyword))


def new_env():
    return lisp.Env(outer=lisp.global_env)


def is_user_defined(env, form):
    """True if the step's head was defined by the script's core.rvt files"""
    return head(form) is not None and dict.__contains__(env, form[0])


def call_user_step(env, form):
    fn = env[form[0]]
    if not callable(fn):
        return BlockResult(False, stderr=f"{form[0]} is not a function")
    value = fn(*[lisp.eval(arg, env) for arg in form[1:]])
    return BlockResult(bool(value), stdout=f"returned {edn.writes(value).strip()}")


def run_step(form, env=None):
    """Execute one step form, always returning a BlockResult"""
    try:
        if env is not None and is_user_defined(env, form):
            return call_user_step(env, form)
        block = find_block(form) if len(form) > 0 else None
        if block is None:
            return BlockResult(
                False, stderr=f"No BuildingBlock matches {edn.writes(form).strip()}"
            )
        result = block.execute()
    except Exception:
        return BlockResult(False, stderr=traceback.format_exc())

    if not isinstance(result, BlockResult):
        result = BlockResult(bool(result))
    return result


def load_definitions(env, text, keep=frozenset()):
    """Evaluate the def and defn forms of a core.rvt into `env`.

    Names in `keep` are already defined and are not overridden.
    """
    for form in edn.read_all(text):
        if head(form) in DEFINITIONS and form[1] not in keep:
            lisp.eval(form, env)


def execute_script(text, observer, script=None, env=None):
    """Run the statements of `text` in order. Returns "pass" or "fail"."""
    env = env if env is not None else new_env()
    forms = list(edn.read_all(text))
    observer.on_procedure_begin(script=script, statements=len(forms))

    passed = True
    for index, form in enumerate(forms):
        if is_comment(form):
            observer.on_comment(index=index, text=form)
        elif isinstance(form, list) and head(form) not in DIRECTIVES:
            observer.on_step_start(index=index, form=edn.writes(form).strip())
            started = time.monotonic()
            result = run_step(form, env)
            observer.on_step_end(
                index=index,
                passed=bool(result),
                stdout=result.stdout,
                stderr=result.stderr,
                duration=round(time.monotonic() - started, 3),
            )
            if not result:
                passed = False
                break

    outcome = "pass" if passed else "fail"
    observer.on_procedure_end(outcome=outcome)
    return outcome


def build_env(files, load_order, imports=()):
    """An env holding the definitions of every core.rvt in the closure.

    Files in `imports` only add definitions: they never override a name
    defined by the script's own core.rvt chain. Only def and defn forms
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
    return env


def variation_values(env, variation):
    """symbol -> value for a Variation, evaluated in `env`"""
    return {
        symbol: lisp.eval(form, env)
        for symbol, form in zip(variation.symbols, variation.forms)
    }


def find_variation(text, name):
    for form in edn.read_all(text):
        if head(form) == "variations":
            errors = []
            for variation in parse_variations("", form, errors):
                if variation.name == name:
                    return variation
    raise ValueError(f"No variation named {name}")


def execute_closure(files, load_order, observer, imports=(), variation=None):
    """Load the core.rvt files in order, then run the script (last).

    With `variation` (a name), that variation's symbols are bound before
    the script runs.
    """
    env = build_env(files, load_order, imports)
    script = load_order[-1]
    if variation is not None:
        values = variation_values(env, find_variation(files[script], variation))
        env.update({edn.Symbol(symbol): value for symbol, value in values.items()})
    return execute_script(files[script], observer, script=script, env=env)
