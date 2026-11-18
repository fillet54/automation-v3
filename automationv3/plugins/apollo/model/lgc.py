"""The lunar module guidance computer (LGC): navigation, guidance, the
executive, alarms, and the DSKY

Everything here works on the flight's state dict (see sim.py) and
decides what the computer commands; vehicle.py carries it out.

Programs:

- P63, braking: waits for the crew's PRO at ignition (V99 N62 flashing),
  then flies to high gate.
- P64, approach: flies from high gate to low gate.
- P65, automatic vertical descent at 1 m/s, if the crew hasn't taken
  P66 by the end of the approach.
- P66, rate of descent: holds the commanded rate with the throttle;
  each click of the ROD switch changes it by 1 ft/s.
- P68, landing confirmed: no further thrust.
- P70, abort with the descent engine; P71, abort stage.
- P00, idling, on the surface.
"""

import math

from . import missions as M
from .rope import flags

GUIDANCE_TICKS = 20  # the servicer's 2-second cycle, in 0.1 s ticks
FT = 0.3048
TILT_LIMIT = math.radians(20)

NOUNS = (60, 62, 63, 64, 68, 93)
VERBS = (6, 16, 35, 37, 57)

# Executive load by program, and what adds to it
BASE_LOAD = {63: 0.80, 64: 0.80, 65: 0.70, 66: 0.70, 68: 0.30, 70: 0.75, 71: 0.75, 0: 0.20}
MONITOR_LOAD = 0.10
RR_COUNTER_LOAD = 0.15
OVERLOAD_LIMIT = 0.6  # seconds of work behind before 1202

ALARM_EXECUTIVE_OVERFLOW = 1202
ALARM_LOAD_MISMATCH = 1520  # the model's own: the erasable load doesn't match the vehicle

LIGHTS = ("prog", "opr-err", "key-rel", "comp-acty", "restart", "alt", "vel")


def fresh(load, rope):
    """The LGC's part of the state at boot, for an erasable `load`"""
    return {
        "load": load,
        "rope": rope,
        "program": 63,
        "ignited": None,  # tick of ignition
        "awaiting_pro": False,
        "lr_incorporate": False,
        "nav": {"h_err": 900.0, "vx_err": 1.0},
        "throttle_cmd": 0.0,
        "full_throttle": True,
        "thrust_angle": 0.0,
        "vz_cmd": None,
        "alarms": [],
        "restarts": 0,
        "overload": 0.0,
        "load_fraction": BASE_LOAD[63],
        "monitor": None,  # noun the crew is monitoring (V16)
        "display": {"verb": 0, "noun": 0, "r": [0.0, 0.0, 0.0]},
        "flashing": False,
        "program_display": None,  # [verb, noun] the program wants
        "frozen": None,  # V06: the values shown when it was keyed
        "lights": {name: False for name in LIGHTS},
        "lamp_test_until": None,
        "entry": {"mode": None, "verb": "", "noun": "", "digits": ""},
        "cfg_ok": True,
        "phase_tgo": 0.0,
    }


def g_eff(s):
    return M.G_MOON - s["vx"] ** 2 / (M.R_MOON + s["h"])


# Navigation


def nav(s):
    """The state as the computer knows it"""
    n = s["lgc"]["nav"]
    return {"x": s["x"], "h": s["h"] + n["h_err"], "vx": s["vx"] + n["vx_err"], "vz": s["vz"]}


def incorporate(s, lr):
    """Take in the landing radar, once the crew has enabled it (V57)"""
    lgc = s["lgc"]
    if not lgc["lr_incorporate"] or s["landed"]:
        return
    n = lgc["nav"]
    if lr["alt_good"]:
        n["h_err"] += 0.35 * (lr["alt"] - (s["h"] + n["h_err"]))
    if lr["vel_good"]:
        n["vx_err"] *= 0.65


# Guidance


def mission(s):
    return M.MISSIONS[s["lgc"]["load"]]


def gate(s):
    """The current phase's target: high gate in P63, low gate in P64"""
    lgc = s["lgc"]
    if lgc["ignited"] is None or lgc["program"] not in (63, 64):
        return None
    return mission(s)["high_gate" if lgc["program"] == 63 else "low_gate"]


def quadratic(r, v, rt, vt, tgo):
    """Acceleration now, for a linearly changing acceleration that
    reaches position rt with velocity vt in tgo seconds"""
    return 6 * (rt - r) / tgo ** 2 - 2 * (2 * v + vt) / tgo


def command_thrust(s, ax, az):
    """Throttle and thrust direction for the acceleration (ax, az),
    gravity included"""
    lgc = s["lgc"]
    tax, taz = ax, az + g_eff(s)
    lgc["thrust_angle"] = math.atan2(tax, taz)
    lgc["throttle_cmd"] = s["m"] * math.hypot(tax, taz) / M.DESCENT_MAX_N


def guide(s):
    """One guidance cycle (every 2 s) for P63 and P64.

    Downrange, guidance commands the constant deceleration that reaches
    the gate's velocity at the gate; the time that takes is the time to
    go. Vertically, it flies to the gate's altitude and rate in that
    time. Ahead of the plan, the next cycle asks for less, so the engine
    throttles down from full throttle on its own as the LM gets lighter
    (the "throttle down" of the braking phase)."""
    lgc = s["lgc"]
    target = gate(s)
    if target is None:
        return
    n = nav(s)
    to_go = target["x"] - n["x"]
    speed = max(n["vx"], target["vx"] + 0.1)
    tgo = 2 * to_go / (speed + target["vx"]) if to_go > 0 else 0.0
    lgc["phase_tgo"] = round(max(tgo, 0.0), 1)
    if tgo <= 2.5:
        if lgc["program"] == 63:
            change_program(s, 64)
            return guide(s)
        else:
            change_program(s, 65)
            lgc["vz_cmd"] = -1.0
        return
    ax = -(speed ** 2 - target["vx"] ** 2) / (2 * to_go)
    az = max(-1.5, min(1.5, quadratic(n["h"], n["vz"], target["h"], target["vz"], tgo)))
    command_thrust(s, ax, az)


def hold_rate(s):
    """P65 and P66, every tick: hold the commanded rate of descent with
    the throttle, and null horizontal velocity within the tilt limit"""
    lgc = s["lgc"]
    n = nav(s)
    ax = max(-1.0, min(1.0, -0.35 * n["vx"]))
    az = 1.5 * (lgc["vz_cmd"] - n["vz"])
    tax, taz = ax, az + g_eff(s)
    angle = max(-TILT_LIMIT, min(TILT_LIMIT, math.atan2(tax, taz)))
    lgc["thrust_angle"] = angle
    lgc["throttle_cmd"] = s["m"] * taz / math.cos(angle) / M.DESCENT_MAX_N


def abort_guidance(s):
    """P70 and P71: full thrust, upright, climbing"""
    lgc = s["lgc"]
    lgc["thrust_angle"] = 0.0
    lgc["throttle_cmd"] = 1.0


def click_rod(s, clicks):
    """The rate-of-descent switch: the first click selects P66; each
    one after changes the commanded rate by 1 ft/s (up is positive)"""
    lgc = s["lgc"]
    if s["landed"] or lgc["program"] not in (64, 65, 66):
        return False
    if lgc["program"] != 66:
        change_program(s, 66)
        rate = nav(s)["vz"]
        lgc["vz_cmd"] = round(rate / FT) * FT
        clicks -= 1 if clicks > 0 else -1
    lgc["vz_cmd"] += clicks * FT
    return True


def change_program(s, program):
    lgc = s["lgc"]
    lgc["program"] = program
    event(s, "program", program=program)
    shown = {63: [6, 63], 64: [6, 64], 65: [6, 60], 66: [6, 60], 68: [6, 60],
             70: [6, 62], 71: [6, 62], 0: [0, 0]}[program]
    request_display(s, shown)


def request_display(s, shown, flashing=False):
    lgc = s["lgc"]
    lgc["program_display"] = shown
    lgc["flashing"] = flashing
    if lgc["monitor"] is not None:
        lgc["lights"]["key-rel"] = True  # the program wants the DSKY back
    else:
        show(s, *shown)


def show(s, verb, noun):
    lgc = s["lgc"]
    lgc["display"]["verb"], lgc["display"]["noun"] = verb, noun
    lgc["frozen"] = noun_values(s, noun) if verb == 6 else None
    refresh(s)


def refresh(s):
    """Put the noun's current values in R1-R3 (V16), or keep V06's"""
    lgc = s["lgc"]
    d = lgc["display"]
    d["r"] = list(lgc["frozen"]) if lgc["frozen"] is not None else noun_values(s, d["noun"])


def prop_percent(s):
    lgc = s["lgc"]
    if flags(lgc["rope"])["prop_capacity_from_load"]:
        capacity = mission(s)["propellant"]
    else:
        capacity = M.MISSIONS["standard"]["propellant"]
    return 100.0 * s["prop_d"] / capacity


def noun_values(s, noun):
    n = nav(s)
    lgc = s["lgc"]
    r = lambda v: round(v, 1)  # noqa: E731
    if noun == 60:
        return [r(n["vx"]), r(n["vz"]), r(n["h"])]
    if noun == 62:
        since = 0.0 if lgc["ignited"] is None else (s["tick"] - lgc["ignited"]) / 10.0
        return [r(math.hypot(n["vx"], n["vz"])), r(since), r(s["delta_v"])]
    if noun == 63:
        return [r(n["h"]), r(n["vz"]), r(delta_h(s))]
    if noun == 64:
        look = math.degrees(math.atan2(n["h"], max(-n["x"], 1.0)))
        return [r(look), r(n["vz"]), r(n["h"])]
    if noun == 68:
        return [r(math.hypot(n["x"], n["h"])), r(lgc["phase_tgo"]), r(delta_h(s))]
    if noun == 93:
        return [r(prop_percent(s)), r(s["prop_d"]), 0.0]
    return [0.0, 0.0, 0.0]


def delta_h(s):
    """Radar altitude less computed altitude, while the radar's good"""
    lr = s["lr"]
    if not lr["alt_good"]:
        return 0.0
    return lr["alt"] - nav(s)["h"]


# The executive


def executive(s, seconds):
    """The computer's load over one guidance cycle: overflow raises
    1202, restarts, and drops the monitor job"""
    lgc = s["lgc"]
    load = BASE_LOAD.get(lgc["program"], 0.5)
    if lgc["monitor"] is not None:
        load += MONITOR_LOAD
    if s["panel"]["rr_mode"] == "auto" and s["bench"]["rr_cdu_fault"]:
        load += RR_COUNTER_LOAD
    lgc["load_fraction"] = round(load, 3)
    if load > 1.0:
        lgc["overload"] += (load - 1.0) * seconds
    else:
        lgc["overload"] = 0.0
    if lgc["overload"] >= OVERLOAD_LIMIT:
        lgc["overload"] = 0.0
        program_alarm(s, ALARM_EXECUTIVE_OVERFLOW)
        lgc["restarts"] += 1
        lgc["lights"]["restart"] = True
        if lgc["monitor"] is not None:
            lgc["monitor"] = None
            lgc["lights"]["key-rel"] = False
            if lgc["program_display"]:
                show(s, *lgc["program_display"])


def program_alarm(s, code):
    lgc = s["lgc"]
    lgc["alarms"].append(code)
    lgc["lights"]["prog"] = True
    event(s, "program-alarm", code=code)


# Ignition and the configuration check


def check_load(s):
    """At P63: does the erasable load match the vehicle? The load says
    how much propellant to expect; the gauges say what is there."""
    expected = mission(s)["propellant"]
    ok = abs(s["prop_d"] - expected) <= 0.03 * expected
    s["lgc"]["cfg_ok"] = ok
    if ok:
        request_display(s, [99, 62], flashing=True)
        s["lgc"]["awaiting_pro"] = True
    else:
        program_alarm(s, ALARM_LOAD_MISMATCH)
        show(s, 6, 93)


def proceed(s):
    lgc = s["lgc"]
    if lgc["awaiting_pro"]:
        lgc["awaiting_pro"] = False
        lgc["flashing"] = False
        lgc["ignited"] = s["tick"]
        event(s, "ignition")
        lgc["program_display"] = [6, 63]
        if lgc["monitor"] is None:
            show(s, 6, 63)
        guide(s)


# The DSKY's keys


def key(s, k):
    """One key: V N 0-9 + - E(ENTR) P(PRO) R(RSET) K(KEY REL) C(CLR)"""
    lgc = s["lgc"]
    e = lgc["entry"]
    if k == "V":
        e.update(mode="verb", verb="", noun="")
    elif k == "N":
        e.update(mode="noun", noun="")
    elif k.isdigit():
        if e["mode"] == "verb" and len(e["verb"]) < 2:
            e["verb"] += k
        elif e["mode"] == "noun" and len(e["noun"]) < 2:
            e["noun"] += k
        elif e["mode"] == "program" and len(e["digits"]) < 2:
            e["digits"] += k
        else:
            operator_error(s)
    elif k in "+-":
        operator_error(s) if e["mode"] is None else None
    elif k == "E":
        enter(s)
    elif k == "P":
        proceed(s)
    elif k == "R":
        reset(s)
    elif k == "K":
        key_release(s)
    elif k == "C":
        e.update(mode=None, verb="", noun="", digits="")
    else:
        raise ValueError(f"no DSKY key {k!r}")


def operator_error(s):
    lgc = s["lgc"]
    lgc["lights"]["opr-err"] = True
    lgc["entry"].update(mode=None, verb="", noun="", digits="")
    event(s, "operator-error")


def enter(s):
    lgc = s["lgc"]
    e = lgc["entry"]
    if e["mode"] == "program":
        digits, e["digits"], e["mode"] = e["digits"], "", None
        return change_by_keyboard(s, int(digits) if digits else -1)
    if len(e["verb"]) != 2:
        return operator_error(s)
    verb = int(e["verb"])
    noun = int(e["noun"]) if len(e["noun"]) == 2 else None
    e.update(mode=None, verb="", noun="")
    if verb not in VERBS:
        return operator_error(s)
    if verb in (6, 16):
        if noun not in NOUNS:
            return operator_error(s)
        lgc["monitor"] = noun if verb == 16 else None
        lgc["lights"]["key-rel"] = False
        show(s, verb, noun)
    elif verb == 35:
        lgc["lamp_test_until"] = s["tick"] + 50
    elif verb == 37:
        e["mode"] = "program"
        e["digits"] = ""
    elif verb == 57:
        if s["landed"]:
            return operator_error(s)
        lgc["lr_incorporate"] = True
        event(s, "landing-radar-enabled")


def change_by_keyboard(s, program):
    """V37: change program. P00 only once landed; P70 and P71 at any time
    before landing; nothing else."""
    lgc = s["lgc"]
    if program == 0 and s["landed"]:
        change_program(s, 0)
    elif program == 70 and not s["landed"] and not s["staged"]:
        start_abort(s)
    elif program == 71 and not s["landed"]:
        s["panel"]["abort_stage"] = True
    else:
        operator_error(s)
    return lgc["program"]


def start_abort(s):
    if s["lgc"]["program"] not in (70, 71) and not s["landed"]:
        change_program(s, 70)
        event(s, "abort")


def reset(s):
    """RSET: clear the error lights once their cause has passed"""
    lights = s["lgc"]["lights"]
    lights["opr-err"] = False
    lights["prog"] = False
    lights["restart"] = False


def key_release(s):
    lgc = s["lgc"]
    lgc["monitor"] = None
    lgc["lights"]["key-rel"] = False
    if lgc["program_display"]:
        show(s, *lgc["program_display"])


def displayed_lights(s):
    """The DSKY's lights, as the crew sees them (lamp test lights all)"""
    lgc = s["lgc"]
    if lgc["lamp_test_until"] is not None and s["tick"] < lgc["lamp_test_until"]:
        return {name: True for name in LIGHTS}
    return dict(lgc["lights"])


def update_lights(s):
    lgc = s["lgc"]
    flying = not s["landed"] and lgc["program"] in (63, 64, 65, 66)
    lgc["lights"]["alt"] = flying and not s["lr"]["alt_good"]
    lgc["lights"]["vel"] = flying and not s["lr"]["vel_good"]
    lgc["lights"]["comp-acty"] = lgc["load_fraction"] >= 0.75 and not s["landed"]
    if lgc["lamp_test_until"] is not None and s["tick"] >= lgc["lamp_test_until"]:
        lgc["lamp_test_until"] = None


def event(s, kind, **detail):
    s["events"].append({"t": round(s["tick"] / 10.0, 1), "kind": kind, **detail})
