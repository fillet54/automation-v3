"""A flight of the lunar module: one JSON-serialisable state dict, and
the functions that boot it and run it forward

Time goes in ticks of 0.1 s. While the LM flies, every tick is
simulated; on the surface, the simulation takes minute-long steps, so a
three-day surface stay costs a few thousand steps.

    s = boot(rope, {"mission": "extended", "start": "high-gate"})
    advance(s, 60)
    s["h"], s["lgc"]["program"]

A flight is deterministic: the same rope, configuration and environment
give the same flight. The seed adds sensor noise (0: none).
"""

import copy

from . import crew as C
from . import lgc as L
from . import missions as M
from . import vehicle as V
from .rope import flags

DEFAULTS = {"mission": "standard", "vehicle": None, "start": "pdi", "crew": "nominal", "seed": 0}
FLY_LIMIT_S = 1200


class BootRejected(Exception):
    """The rope won't take this erasable load"""


class StartUnreachable(Exception):
    """The flight never got to the start point asked for"""


def configuration(config=None):
    """The full boot configuration, checked, from a partial one"""
    c = {**DEFAULTS, **{k: v for k, v in (config or {}).items() if v is not None}}
    c["vehicle"] = c["vehicle"] or c["mission"]
    for key, allowed in (("mission", M.MISSIONS), ("vehicle", M.VEHICLES),
                         ("start", M.START_POINTS), ("crew", M.CREWS)):
        if c[key] not in allowed:
            raise ValueError(f"{key} must be one of {', '.join(allowed)}, not {c[key]!r}")
    unknown = set(c) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown boot settings: {', '.join(sorted(unknown))}")
    c["seed"] = int(c["seed"])
    return c


def at_pdi(rope, config, env=None):
    """A fresh flight at powered descent initiation"""
    c = configuration(config)
    if c["mission"] == "extended" and not flags(rope)["extended_missions"]:
        raise BootRejected(f"{rope['revision']} has no extended missions")
    pdi = M.MISSIONS[c["mission"]]["pdi"]
    s = {
        "model": M.MODEL_VERSION,
        "config": c,
        "env": dict(env or {}),
        "tick": 0,
        "start_tick": 0,
        "events": [],
        "trajectory": [],
        "panel": {"abort": False, "abort_stage": False, "engine_stop": False,
                  "master_arm": False, "engine_arm": "des", "rr_mode": "lgc"},
        "bench": {"lr_failed": False, "rr_cdu_fault": False, "battery_faults": {},
                  "bus_load_amps": 0.0, "o2_leak_kg_h": 0.0},
        "fixed": {},
        "crew": C.fresh("nominal"),
        **V.fresh(c["vehicle"], pdi),
    }
    s["lgc"] = L.fresh(c["mission"], rope)
    V.landing_radar(s)
    L.check_load(s)
    V.record(s)
    return s


REACHED = {
    "pdi": lambda s: True,
    "high-gate": lambda s: s["lgc"]["program"] == 64,
    "low-gate": lambda s: s["lgc"]["program"] == 64 and s["lgc"]["phase_tgo"] <= 10.0,
    "surface": lambda s: s["landed"] and s["touchdown"] and s["tick"] >= s["touchdown"]["t"] * 10 + 600,
}


def boot(rope, config=None, env=None):
    """Boot the LM for `config`, flown by the nominal crew to its start
    point, then handed to the configuration's crew"""
    c = configuration(config)
    s = at_pdi(rope, c, env)
    if c["start"] != "pdi":
        reached = REACHED[c["start"]]
        run_until(s, reached, FLY_LIMIT_S if c["start"] != "surface" else FLY_LIMIT_S + 120)
        if not reached(s):
            raise StartUnreachable(f"the flight didn't reach {c['start']}")
    s["crew"] = C.fresh(c["crew"])
    s["start_tick"] = s["tick"]
    return s


def at_start(s):
    return s["tick"] == s["start_tick"]


def step(s, n):
    """Run n ticks as one step"""
    dt = n / 10.0
    if s["fixed"]:
        apply_fixed(s)
    C.act(s)
    V.panel(s)
    if not s["landed"]:
        V.landing_radar(s)
        lgc = s["lgc"]
        if s["tick"] % L.GUIDANCE_TICKS == 0:
            L.incorporate(s, s["lr"])
            L.executive(s, L.GUIDANCE_TICKS / 10.0)
            L.guide(s)
            if lgc["display"]["verb"] == 16:
                L.refresh(s)
        if lgc["program"] in (65, 66):
            L.hold_rate(s)
        elif lgc["program"] in (70, 71):
            L.abort_guidance(s)
        V.deca(s)
        V.move(s, dt)
        V.contact(s)
    V.power(s, dt)
    V.environment(s, dt)
    V.caution_and_warning(s)
    L.update_lights(s)
    s["tick"] += n
    V.record(s)


def advance(s, seconds):
    """Run the flight forward"""
    end = s["tick"] + round(seconds * 10)
    while s["tick"] < end:
        n = min(600 - s["tick"] % 600, end - s["tick"]) if s["landed"] else 1
        step(s, n)
    return s["tick"] / 10.0


def run_until(s, condition, limit_s):
    """Run until condition(s) holds, at most limit_s seconds; true if it did"""
    end = s["tick"] + round(limit_s * 10)
    while not condition(s) and s["tick"] < end:
        step(s, 600 - s["tick"] % 600 if s["landed"] else 1)
    return condition(s)


# Inputs held every step (SetFixedValue): path -> value, applied by the
# plugin's write function before each step. The model keeps them as data.
_fixers = {}


def apply_fixed(s):
    for path, value in s["fixed"].items():
        fixer = _fixers.get(path)
        if fixer:
            fixer(s, value)


def copy_state(s):
    return copy.deepcopy(s)
