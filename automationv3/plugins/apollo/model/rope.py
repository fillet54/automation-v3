"""The guidance computer's software: the Luminary revisions

A rope is the program woven into the LGC's fixed memory. Here a rope is
a small JSON document: the revision it is, and the flags that decide how
it behaves. Released ropes are below; a local build is a
``luminary.json`` file in the same format, so a developer can change a
flag and try the result.

The revisions and the missions they flew on are real. Their mission
support is close to history: the extended lunar module first flew with
Luminary 1E on Apollo 15. The defect in LUM131 is invented for this
example: with an extended mission's load it computes the propellant
remaining against the standard load, so the display reads high and the
PROPELLANT LOW caution comes on late.
"""

import hashlib
import json

FLAGS = {
    # Accepts an erasable load for an extended mission
    "extended_missions": False,
    # Propellant remaining is a share of the propellant the load says
    # was loaded (false: of the standard mission's)
    "prop_capacity_from_load": True,
}

RELEASES = {
    "LUM099": {"revision": "LUM099", "flew": "Apollo 11",
               "flags": {"extended_missions": False, "prop_capacity_from_load": True}},
    "LUM131": {"revision": "LUM131", "flew": "Apollo 13",
               "flags": {"extended_missions": True, "prop_capacity_from_load": False}},
    "LUM210": {"revision": "LUM210", "flew": "Apollo 15 to 17",
               "flags": {"extended_missions": True, "prop_capacity_from_load": True}},
}


def canonical(rope):
    """The rope as the bytes its digest is taken of"""
    return json.dumps(rope, sort_keys=True, separators=(",", ":")).encode()


def digest(rope):
    return hashlib.sha256(canonical(rope)).hexdigest()


def flags(rope):
    return {**FLAGS, **(rope or {}).get("flags", {})}


def parse(text):
    """A rope from a luminary.json file's text; ValueError if it isn't one"""
    rope = json.loads(text)
    if not isinstance(rope, dict) or not isinstance(rope.get("revision"), str):
        raise ValueError("a rope is a JSON object with a \"revision\"")
    unknown = set(rope.get("flags", {})) - set(FLAGS)
    if unknown:
        raise ValueError(f"unknown rope flags: {', '.join(sorted(unknown))}")
    return rope
