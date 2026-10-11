from automationv3.framework import html
from automationv3.framework.block import PLACEHOLDER, BlockResult, BuildingBlock
from automationv3.framework.language import is_text


class TBD(BuildingBlock):
    """A step that isn't written yet: what it will do, in words.

    Write a test's flow first as ``rvt`` blocks titled with what each step
    will do, holding just ``(TBD)``, so it can be reviewed as a whole, then
    replace each with real steps. Where a step has no block of its own
    (inside code, or among a table block's steps), give it the words. A run
    reports a ``TBD`` as *to do* and goes on, so the steps around it still
    run; a run that reaches one can't pass: if nothing else fails, its
    outcome is *incomplete*, and its requirements don't roll up green.

    Used where a value is expected (a precondition's check, an ``if``), a
    ``TBD`` comes out true, so the flow after it can be reviewed too.

    Examples::

        .. rvt:: Set the autopilot engage switch to ON

           (TBD)

        (TBD "Set the autopilot engage switch to ON")
    """

    kind = PLACEHOLDER

    def usage(self):
        return '(TBD)\n(TBD "what the step will do")'

    def check_syntax_forms(self, *args):
        return not args or (len(args) == 1 and is_text(args[0]))

    def execute_forms(self, description=None):
        return BlockResult(True, value=True)

    def as_html(self, description=None):
        text = "" if description is None else (
            f' <span class="ui-tbd__text">{html.text(description)}</span>')
        return ('<div class="ui-tbd"><span class="ui-tbd__label">To be written</span>'
                f'{text}</div>')
