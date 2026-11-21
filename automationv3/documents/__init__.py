"""Documents rendered from reStructuredText and data

Scripts, run results and reports are all reStructuredText. Where a
document shows data (a run's results, a report's rollup), it says so
with a directive or role that leaves a placeholder when parsed, and is
resolved against the data later (see core.py). What a placeholder
resolves to is itself reStructuredText, written by a snippet (see
template.py), so every output (live HTML, a static site, a PDF) renders
the same source in its own way.
"""

from pathlib import Path

from . import core, report, run  # noqa: F401  (registers the directives)
from . import registry  # noqa: F401  (attaches plugin rendering registry)

STATIC = Path(__file__).parent / "static"
