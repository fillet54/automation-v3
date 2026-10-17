"""Word-level differences between two versions of a requirement's text"""

import difflib
import re

# Words (with their units: 40%, 1.5, C/5), each punctuation mark, and spaces
WORDS = re.compile(r"\w(?:[\w%/]|[.,]\w)*%?|[^\w\s]|\s+")


def word_diff(before, after):
    """[(op, text)]: op is "same", "removed" or "added"; joined in order,
    the "same" and "removed" parts give `before` and the "same" and
    "added" parts give `after`"""
    a, b = WORDS.findall(before or ""), WORDS.findall(after or "")
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(("same", "".join(a[i1:i2])))
            continue
        if i2 > i1:
            out.append(("removed", "".join(a[i1:i2])))
        if j2 > j1:
            out.append(("added", "".join(b[j1:j2])))
    return out


def dict_diff(before, after):
    """[(key, before value, after value)] for keys whose values differ"""
    before, after = before or {}, after or {}
    return [(k, before.get(k), after.get(k)) for k in sorted(before.keys() | after.keys())
            if before.get(k) != after.get(k)]
