"""What scripts see as `lm`: the lunar module, its crew station and the
simulator's bench

Methods are called with the dot form, e.g. (.mission lm). They take and
give edn: keywords for enumerations (:extended), maps with keyword keys.
Actions return true, so a call can be a step.
"""

import time

from automationv3.framework import edn
from automationv3.framework.clock import SimClock

from . import connectors as C
from .model import lgc as L
from .model import sim

# Where a flight can be flown to with FlyTo, and how to tell it got there
PHASES = {
    "ignition": lambda s: s["lgc"]["ignited"] is not None,
    "throttle-down": lambda s: any(e["kind"] == "throttle-down" for e in s["events"]),
    "high-gate": lambda s: any(e["kind"] == "program" and e["program"] == 64 for e in s["events"]),
    "low-gate": lambda s: (s["lgc"]["program"] == 64 and s["lgc"]["phase_tgo"] <= 10.0)
    or s["lgc"]["program"] in (65, 66, 68) or s["landed"],
    "p66": lambda s: s["lgc"]["program"] == 66,
    "contact": lambda s: s["contact"],
    "touchdown": lambda s: s["landed"],
}


def name(value):
    return C.name(value)


def to_edn(value):
    if isinstance(value, dict):
        return edn.Map({edn.Keyword(str(k).replace("_", "-")): to_edn(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return edn.Vector(to_edn(v) for v in value)
    return value


ENUMERATED = {"mission", "vehicle", "start", "crew", "kind", "light"}


def edn_config(config):
    return edn.Map({edn.Keyword(k): (edn.Keyword(v) if k in ENUMERATED and isinstance(v, str)
                                     else v) for k, v in config.items()})


class LunarModuleHandle:
    def __init__(self, uut, env, wall=time.time, sleep=time.sleep):
        self.uut, self.env = uut, env
        self.wall, self.sleep = wall, sleep

    @property
    def pace(self):
        return getattr(self.env, "pace", None)

    # Loading and saving the flight, caught up with the wall clock in lms

    def _load(self):
        state = self.uut.load(self.env)
        if state["flight"] is None:
            raise RuntimeError("the lm isn't booted: boot it with StartLM")
        self._catch_up(state)
        return state

    def _catch_up(self, state):
        if not self.pace or state.get("wall") is None:
            return
        ticks = int((self.wall() - state["wall"]) * self.pace * 10)
        if ticks > 0:
            sim.advance(state["flight"], ticks / 10.0)
            state["wall"] += ticks / 10.0 / self.pace
            self.uut.save(self.env, state)

    def _run(self, change):
        state = self._load()
        result = change(state["flight"])
        self.uut.save(self.env, state)
        return result

    def _read(self, look):
        return look(self._load()["flight"])

    # Booting

    def boot(self, config=None):
        """Boot for a configuration map (see StartLM); :accepted, or
        :rejected-load if the installed rope won't take the load"""
        config = {name(k): name(v) for k, v in (config or {}).items()}
        state = self.uut.load(self.env)
        try:
            state["flight"] = self.uut.boot(state["rope"], config, self.env)
        except sim.BootRejected:
            return edn.Keyword("rejected-load")
        state["wall"] = self.wall() if self.pace else None
        self.uut.save(self.env, state)
        return edn.Keyword("accepted")

    def booted(self):
        return self.uut.load(self.env)["flight"] is not None

    def config(self):
        return edn_config(self._read(lambda s: s["config"]))

    def mission(self):
        return edn.Keyword(self._read(lambda s: s["lgc"]["load"]))

    def version(self):
        installed = self.uut.load(self.env)["installed"]
        return installed["id"] if installed else None

    def supports_extended(self):
        from .model.rope import flags
        return flags(self.uut.load(self.env)["rope"])["extended_missions"]

    def at_start(self, start=None):
        """True until the LM has moved since it was booted (at `start`, if given)"""
        if not self.booted():
            return False
        return self._read(lambda s: sim.at_start(s)
                          and (start is None or s["config"]["start"] == name(start)))

    def ready(self, mission, start, crew=edn.Keyword("nominal")):
        """Booted for this mission, at this start point with this crew,
        and not moved since"""
        if not self.booted():
            return False
        c = self._read(lambda s: s["config"])
        return (self.at_start() and c["mission"] == name(mission) and c["start"] == name(start)
                and c["crew"] == name(crew))

    # Time

    def run_for(self, seconds):
        """Run simulated time forward (in lms, wait for it); the time now"""
        if self.pace:
            until = self.read_point("lm.time.sim") + float(seconds)
            while self.read_point("lm.time.sim") < until:
                self.sleep(min(0.05, float(seconds) / self.pace))
            return self.read_point("lm.time.sim")
        return self._run(lambda s: sim.advance(s, float(seconds)))

    def advance(self, seconds):
        """The sim clock's step"""
        self._run(lambda s: sim.advance(s, float(seconds)))

    def clock(self):
        time_ref = C_REF("lm.time.sim")
        return SimClock(time_ref, step=None if self.pace else self.advance)

    def fly_to(self, phase, limit=1500):
        """Run until a phase of the flight (see PHASES); true if it got there"""
        reached = PHASES[name(phase)]
        if self.pace:
            end = self.read_point("lm.time.sim") + float(limit)
            while not self._read(reached) and self.read_point("lm.time.sim") < end:
                self.sleep(0.05)
            return self._read(reached)
        return self._run(lambda s: sim.run_until(s, reached, float(limit)))

    # The crew station

    def keys(self, text):
        """Key the DSKY (V N 0-9 + - E P R K C; spaces ignored); the
        display afterwards"""
        for k in str(text).upper().replace(" ", ""):
            self._run(lambda s: L.key(s, k))
            key_time = self._read(lambda s: s["env"].get("key_time", 0.0))
            if self.pace and key_time:
                self.sleep(key_time / self.pace)
        return self.display()

    def display(self):
        def look(s):
            d = s["lgc"]["display"]
            return edn.Map({edn.Keyword("verb"): d["verb"], edn.Keyword("noun"): d["noun"],
                            edn.Keyword("r1"): d["r"][0], edn.Keyword("r2"): d["r"][1],
                            edn.Keyword("r3"): d["r"][2],
                            edn.Keyword("flashing"): s["lgc"]["flashing"]})
        return self._read(look)

    def click_rod(self, clicks):
        """Clicks of the rate-of-descent switch (negative: down); false if
        the switch does nothing now"""
        return self._run(lambda s: L.click_rod(s, int(clicks)))

    def push_master_alarm(self):
        def push(s):
            s["cwea"]["master_alarm"] = False
            return True
        return self._run(push)

    # The flight so far

    def trajectory(self):
        keys = ("t", "x", "h", "vx", "vz", "throttle", "program", "propellant")
        return edn.Vector(edn.Map({edn.Keyword(k): v for k, v in zip(keys, row)})
                          for row in self._read(lambda s: s["trajectory"]))

    def trajectory_rows(self):
        return self._read(lambda s: [list(row) for row in s["trajectory"]])

    def throttles(self, since=None):
        """Every throttle setting the trajectory recorded, percent; with
        `since` (an event, e.g. :throttle-down), only those after it"""
        def look(s):
            start = None
            if since is not None:
                start = next((e["t"] for e in s["events"] if e["kind"] == name(since)), None)
                if start is None:
                    return []
            return [row[5] for row in s["trajectory"] if start is None or row[0] > start]
        return edn.Vector(self._read(look))

    def events(self, kind=None):
        def look(s):
            return [e for e in s["events"] if kind is None or e["kind"] == name(kind)]
        return edn.Vector(edn_config(e) for e in self._read(look))

    def touchdown(self):
        found = self._read(lambda s: s["touchdown"])
        return to_edn(found) if found else None

    def snapshot(self):
        return self._read(lambda s: s)

    # Connectors

    def read_point(self, path):
        return self._read(lambda s: C.read(s, path))

    def set_point(self, path, value):
        return self._run(lambda s: C.write(s, path, value))

    def fix_point(self, path, value):
        return self._run(lambda s: C.fix(s, path, value))

    def release_point(self, path):
        return self._run(lambda s: C.release(s, path))


def C_REF(path):
    from .blocks import Connector
    return Connector(path)
