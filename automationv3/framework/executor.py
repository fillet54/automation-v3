"""Executes edn test scripts, reporting progress to an observer

Each top-level form is a statement. Plain strings are documentation and
are reported as comments; lists are steps run through their
BuildingBlock. Statement indexes match `testcase.get_statements`, so a
report can line results up with the rendered script.

The first failing step stops the script: the outcome is "fail" and
later statements are not reported.
"""

import time
import traceback

from . import edn
from .block import BlockResult, find_block


def is_comment(form):
    return isinstance(form, str) and not isinstance(form, (edn.Symbol, edn.Keyword))


def run_step(form):
    """Execute one step form, always returning a BlockResult"""
    block = find_block(form) if len(form) > 0 else None
    if block is None:
        return BlockResult(
            False, stderr=f"No BuildingBlock matches {edn.writes(form).strip()}"
        )

    try:
        result = block.execute()
    except Exception:
        return BlockResult(False, stderr=traceback.format_exc())

    if not isinstance(result, BlockResult):
        result = BlockResult(bool(result))
    return result


def execute_script(text, observer, script=None):
    """Run the statements of `text` in order. Returns "pass" or "fail"."""
    forms = list(edn.read_all(text))
    observer.on_procedure_begin(script=script, statements=len(forms))

    passed = True
    for index, form in enumerate(forms):
        if is_comment(form):
            observer.on_comment(index=index, text=form)
        elif isinstance(form, list):
            observer.on_step_start(index=index, form=edn.writes(form).strip())
            started = time.monotonic()
            result = run_step(form)
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
