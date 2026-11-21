"""Requirements as scripts see them: an id, optionally with its text

A requirement's text is reStructuredText, so it can hold lists and
emphasis; a plain sentence is valid rst too.
"""

import re
from dataclasses import dataclass, field

SHALL = re.compile(r"(?<=\s)(shall)(?=\s)", re.IGNORECASE)


@dataclass(frozen=True)
class Requirement:
    id: str
    text: str = None
    subsystem: str = None
    # Where it came from, when it came from a spec: the spec's key, its
    # attributes, the ids it satisfies, its section, its version hash and
    # the hash of its text alone (what a review or a run is against)
    spec: str = None
    attributes: dict = field(default_factory=dict, compare=False, hash=False)
    satisfies: tuple = ()
    section: tuple = ()
    version: str = None
    text_hash: str = None
