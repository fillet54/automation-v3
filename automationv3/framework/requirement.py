"""Requirements as scripts see them: an id, optionally with its text"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Requirement:
    id: str
    text: str = None
    subsystem: str = None

    def __repr_html__(self):
        if self.text:
            markup = re.sub(
                r"\s+shall\s+", f" <strong>shall [{self.id}]</strong> ", self.text
            )
        else:
            markup = f"<strong>[{self.id}]</strong>"
        return f'<span class="ui-requirement">{markup}</span>'
