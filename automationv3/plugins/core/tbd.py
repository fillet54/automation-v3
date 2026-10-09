from automationv3.framework import html
from automationv3.framework.block import PLACEHOLDER, BlockResult, BuildingBlock
from automationv3.framework.language import is_text


class TBD(BuildingBlock):
    """A step that isn't written yet: what it will do, in words.

    Write a test's flow first as titled ``rvt`` blocks of ``TBD`` steps, so
    it can be reviewed as a whole, then replace each with real steps. A run
    reports a ``TBD`` as *to do* and goes on, so the steps around it still
    run; a run that reaches one can't pass: if nothing else fails, its
    outcome is *incomplete*, and its requirements don't roll up green.

    Used where a value is expected (a precondition's check, an ``if``), a
    ``TBD`` comes out true, so the flow after it can be reviewed too.

    Example::

        (TBD "Set the autopilot engage switch to ON")
    """

    kind = PLACEHOLDER

    def usage(self):
        return '(TBD "what the step will do")'

    def check_syntax(self, *args):
        return len(args) == 1 and is_text(args[0])

    def execute_forms(self, description):
        return BlockResult(True, value=True)

    def as_html(self, description):
        return (
            '<div class="ui-tbd"><span class="ui-tbd__label">To be written</span> '
            f'<span class="ui-tbd__text">{html.text(description)}</span></div>'
        )
