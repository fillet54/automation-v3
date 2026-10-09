"""Requirements as scripts see them: an id, optionally with its text

A requirement's text is reStructuredText, so it can hold lists and
emphasis; a plain sentence is valid rst too. Pages show it with each
"shall" marked with the id.
"""

import functools
import re
from dataclasses import dataclass
from html import escape

import docutils.core

SHALL = re.compile(r"(?<=\s)(shall)(?=\s)", re.IGNORECASE)
ONE_PARAGRAPH = re.compile(r"\A\s*<p>(.*)</p>\s*\Z", re.DOTALL)


@functools.lru_cache(maxsize=1024)
def render(id, text):
    """HTML for a requirement's text: inline if it is one paragraph,
    else blocks (lists, several paragraphs)"""
    try:
        html = docutils.core.publish_parts(
            text, writer_name="html4css1",
            settings_overrides={"report_level": 5, "halt_level": 5,
                                "doctitle_xform": False, "initial_header_level": 4},
        )["fragment"]
    except Exception:
        html = f"<p>{escape(text)}</p>"
    html = SHALL.sub(rf"<strong>\1 [{escape(id)}]</strong>", html)
    inline = ONE_PARAGRAPH.match(html)
    if inline and "<p>" not in inline.group(1):
        return f'<span class="ui-requirement">{inline.group(1)}</span>'
    return f'<div class="ui-requirement ui-requirement--blocks">{html}</div>'


@dataclass(frozen=True)
class Requirement:
    id: str
    text: str = None
    subsystem: str = None

    def __repr_html__(self):
        if self.text:
            return render(self.id, self.text)
        return f'<span class="ui-requirement"><strong>[{escape(self.id)}]</strong></span>'
