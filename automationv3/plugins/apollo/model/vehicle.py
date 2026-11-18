"""The lunar module's hardware: the motion, the engines, the sensors,
power, environmental control, and caution and warning

The motion is two-dimensional: downrange x (the landing site is at 0)
and altitude h over a flat Moon, with the centrifugal term that makes
orbital speed weightless. Thrust points along the thrust angle (from
vertical, negative braking), which turns at most 10 degrees a second.
"""

import math
import random

from . import lgc as L
from . import missions as M

ANGLE_RATE = math.radians(10)  # per second


def fresh(vehicle, start):
    v = M.VEHICLES[vehicle]
    return {
        "vehicle": vehicle,
        "x": start["x"], "h": start["h"], "vx": start["vx"], "vz": start["vz"],
        "m": M.pdi_mass(vehicle),
        "prop_d": v["descent_propellant"],
        "prop_a": v["ascent_propellant"],
        "staged": False,
        "thrust_angle": 0.0,
        "throttle": 0.0,
        "des_on": False,
        "asc_on": False,
        "delta_v": 0.0,
        "contact": False,
        "landed": False,
        "crashed": False,
        "touchdown": None,
        "lr": {"alt": 0.0, "alt_good": False, "vel_good": False},
        "eps": {"batteries": [{"ah": M.BATTERY_AH, "fault": False}
                              for _ in range(v["batteries"])],
                "amps": M.LOAD_FLYING_A, "volts": M.BUS_NO_LOAD_V},
        "ecs": {"o2": v["o2"], "water": v["water"]},
        "cwea": {"master_alarm": False, "active": []},
        "throttle_band_violations": 0,
    }


def noise(s, channel, sigma):
    seed = s["config"]["seed"]
    if not seed:
        return 0.0
    return random.Random(f"{seed}:{channel}:{s['tick']}").gauss(0.0, sigma)


def landing_radar(s):
    lr = s["lr"]
    working = not s["bench"]["lr_failed"] and not s["staged"] and not s["landed"]
    dropout = (s["env"].get("terrain") and 300 < s["h"] < 3000
               and (s["tick"] // 10) % 40 < 2)
    lr["alt_good"] = working and not dropout and s["h"] < M.LR_ALTITUDE_GOOD_M
    lr["vel_good"] = working and not dropout and s["h"] < M.LR_VELOCITY_GOOD_M
    lr["alt"] = round(s["h"] + noise(s, "lr", 0.002 * s["h"] + 0.5), 2) if lr["alt_good"] else 0.0


def panel(s):
    """The crew's abort switches"""
    p, lgc = s["panel"], s["lgc"]
    if s["landed"]:
        return
    if p["abort_stage"] and lgc["program"] != 71:
        if p["master_arm"]:
            stage(s)
        elif not s.get("abort_stage_refused"):
            s["abort_stage_refused"] = True
            L.event(s, "abort-stage-refused", why="master arm off")
    elif not p["abort_stage"]:
        s["abort_stage_refused"] = False
    if p["abort"] and lgc["program"] in (63, 64, 65, 66) and lgc["ignited"] is not None:
        L.start_abort(s)


def stage(s):
    """Fire the staging pyros: the descent stage stays behind"""
    v = M.VEHICLES[s["vehicle"]]
    s["staged"] = True
    s["des_on"] = False
    s["m"] -= v["descent_dry"] + s["prop_d"]
    s["prop_d"] = 0.0
    L.change_program(s, 71)
    L.event(s, "staged")


def deca(s):
    """The descent engine control assembly: engine on or off, and the
    throttle, either 10-60% or full throttle, never in between"""
    lgc, p = s["lgc"], s["panel"]
    s["des_on"] = (not s["staged"] and s["prop_d"] > 0 and lgc["ignited"] is not None
                   and lgc["program"] in (63, 64, 65, 66, 70)
                   and not p["engine_stop"] and p["engine_arm"] == "des"
                   and not s["landed"])
    s["asc_on"] = (s["staged"] and lgc["program"] == 71 and s["prop_a"] > 0
                   and not p["engine_stop"] and not s["landed"])
    if not s["des_on"]:
        s["throttle"] = 0.0
        return
    f = lgc["throttle_cmd"]
    if lgc["full_throttle"]:
        if f < M.THROTTLE_RECOVERY:
            lgc["full_throttle"] = False
            L.event(s, "throttle-down")
    elif f > M.THROTTLE_MAX and lgc["program"] == 70:
        lgc["full_throttle"] = True  # an abort goes back to full throttle
    if lgc["full_throttle"]:
        s["throttle"] = M.FULL_THROTTLE
    else:
        s["throttle"] = min(M.THROTTLE_MAX, max(M.THROTTLE_MIN, f))
    if M.THROTTLE_MAX < s["throttle"] < M.FULL_THROTTLE:
        s["throttle_band_violations"] += 1


def move(s, dt):
    lgc = s["lgc"]
    turn = lgc["thrust_angle"] - s["thrust_angle"]
    limit = ANGLE_RATE * dt
    s["thrust_angle"] += max(-limit, min(limit, turn))
    if s["des_on"]:
        force, isp = s["throttle"] * M.DESCENT_MAX_N, M.DESCENT_ISP
    elif s["asc_on"]:
        force, isp = M.ASCENT_N, M.ASCENT_ISP
    else:
        force, isp = 0.0, 1.0
    a = force / s["m"]
    ax = a * math.sin(s["thrust_angle"])
    az = a * math.cos(s["thrust_angle"]) - L.g_eff(s)
    s["vx"] += ax * dt
    s["vz"] += az * dt
    s["x"] += s["vx"] * dt
    s["h"] += s["vz"] * dt
    if force:
        used = force / (isp * M.G0) * dt
        s["m"] -= used
        s["delta_v"] += a * dt
        if s["des_on"]:
            s["prop_d"] = max(0.0, s["prop_d"] - used)
            if s["prop_d"] == 0.0:
                L.event(s, "descent-propellant-depleted")
        else:
            s["prop_a"] = max(0.0, s["prop_a"] - used)


def contact(s):
    lgc = s["lgc"]
    if s["landed"]:
        return
    descending = lgc["program"] in (63, 64, 65, 66, 68) and not s["staged"]
    if descending and not s["contact"] and s["h"] <= M.CONTACT_PROBE_M and s["vz"] <= 0:
        s["contact"] = True
        L.event(s, "contact")
        if lgc["program"] != 68:
            L.change_program(s, 68)
        s["des_on"] = False
    if s["h"] <= 0.0:
        s["touchdown"] = {"t": round(s["tick"] / 10.0, 1), "vz": round(s["vz"], 2),
                          "vx": round(s["vx"], 2), "miss": round(s["x"], 1),
                          "propellant": round(s["prop_d"], 1)}
        s["crashed"] = abs(s["vz"]) > 10.0
        s["landed"] = True
        s["contact"] = True
        s["h"] = 0.0
        s["vx"] = s["vz"] = 0.0
        s["des_on"] = s["asc_on"] = False
        s["throttle"] = 0.0
        L.event(s, "crash" if s["crashed"] else "touchdown", **s["touchdown"])


def power(s, dt):
    eps = s["eps"]
    for n, battery in enumerate(eps["batteries"], 1):
        battery["fault"] = bool(s["bench"]["battery_faults"].get(str(n)))
    amps = (M.LOAD_SURFACE_A if s["landed"] else M.LOAD_FLYING_A) + s["bench"]["bus_load_amps"]
    online = [b for b in eps["batteries"] if not b["fault"] and b["ah"] > 0]
    eps["amps"] = amps
    if not online:
        eps["volts"] = 0.0
        return
    for b in online:
        b["ah"] = max(0.0, b["ah"] - amps * dt / 3600.0 / len(online))
    soc = sum(b["ah"] for b in online) / (M.BATTERY_AH * len(online))
    eps["volts"] = round(max(0.0, M.BUS_NO_LOAD_V - M.BUS_V_PER_A * amps
                             - M.BUS_V_EMPTY_DROP * (1 - soc)) if soc > 0 else 0.0, 2)


def environment(s, dt):
    ecs = s["ecs"]
    hours = dt / 3600.0
    o2 = M.O2_SURFACE_KG_H if s["landed"] else M.O2_FLYING_KG_H
    water = M.WATER_SURFACE_KG_H if s["landed"] else M.WATER_FLYING_KG_H
    ecs["o2"] = max(0.0, ecs["o2"] - (o2 + s["bench"]["o2_leak_kg_h"]) * hours)
    ecs["water"] = max(0.0, ecs["water"] - water * hours)


def caution_and_warning(s):
    v = M.VEHICLES[s["vehicle"]]
    lgc = s["lgc"]
    eps, ecs = s["eps"], s["ecs"]
    active = []
    if lgc["lights"]["prog"]:
        active.append("prog")
    if not s["staged"] and s["prop_d"] < M.LOW_LEVEL_FRACTION * v["descent_propellant"]:
        active.append("des-qty")
    if (lgc["program"] in (63, 64, 65, 66) and lgc["ignited"] is not None
            and L.prop_percent(s) < M.PROPELLANT_LOW_PERCENT):
        active.append("prplnt-low")
    if any(b["fault"] for b in eps["batteries"]) or eps["volts"] < M.BUS_LOW_V:
        active.append("battery")
    if ecs["o2"] < M.ECS_LOW_FRACTION * v["o2"] or ecs["water"] < M.ECS_LOW_FRACTION * v["water"]:
        active.append("ecs")
    if s["bench"]["lr_failed"] and not s["landed"] and not s["staged"]:
        active.append("ldg-rdr")
    if eps["volts"] < M.BUS_MIN_V:
        active.append("bus-warning")
    cwea = s["cwea"]
    for name in active:
        if name not in cwea["active"]:
            cwea["master_alarm"] = True
            L.event(s, "warning" if name == "bus-warning" else "caution", light=name)
    cwea["active"] = active


def record(s):
    every = 6000 if s["landed"] else 10
    if s["tick"] % every == 0 and (not s["trajectory"] or s["trajectory"][-1][0] != s["tick"] / 10):
        s["trajectory"].append([round(s["tick"] / 10.0, 1), round(s["x"], 1), round(s["h"], 1),
                                round(s["vx"], 2), round(s["vz"], 2),
                                round(s["throttle"] * 100, 1), s["lgc"]["program"],
                                round(s["prop_d"], 1)])
