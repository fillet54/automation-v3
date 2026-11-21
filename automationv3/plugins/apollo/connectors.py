"""The lunar module's connectors: every point a script can read, and the
panel switches and bench inputs it can set

A connector is a path, e.g. "lm.dsky.verb". Scripts make one with
(connector "lm.dsky") and reach everything below it with dotted names
(dsky.verb). The panel is the crew's switches; the bench is the
simulator's instructor station, where faults are injected.

Values are edn: enumerations are keywords (:auto), the rest numbers,
booleans and vectors.
"""

from automationv3.framework import edn
from automationv3.framework.refs import Child, Ref

from .model import lgc as L
from .model import missions as M
from .model import sim
from .model import vehicle as V


def keyword(value):
    return edn.Keyword(value) if value is not None else None


def name(value):
    """A keyword's name, or the value as it is"""
    return str(value)[1:] if isinstance(value, edn.Keyword) else value


class Point:
    """One connector: how to read it, and, for an input, how to set it
    (`write`) and what releasing a fixed value leaves (`released`)"""

    def __init__(self, read, write=None, doc="", released=None):
        self.read, self.write_fn, self.doc, self.released = read, write, doc, released

    def write(self, s, value):
        if self.write_fn is None:
            raise PermissionError("read-only")
        self.write_fn(s, value)


def _panel(key, convert=bool, allowed=None):
    def write(s, value):
        value = convert(name(value))
        if allowed and value not in allowed:
            raise ValueError(f"must be one of {', '.join(':' + a for a in allowed)}")
        s["panel"][key] = value
    return write


def _bench(key, convert=bool):
    def write(s, value):
        s["bench"][key] = convert(value)
    return write


def _battery_fault(n):
    def write(s, value):
        faults = s["bench"]["battery_faults"]
        if value:
            faults[str(n)] = True
        else:
            faults.pop(str(n), None)
    return write


def _met(s):
    total = int(M.MET_AT_PDI + s["tick"] / 10)
    return f"{total // 3600}:{total // 60 % 60:02d}:{total % 60:02d}"


def _light(name_):
    return lambda s: L.displayed_lights(s)[name_]


def _caution(name_):
    return lambda s: name_ in s["cwea"]["active"]


def _touchdown(key):
    return lambda s: (s["touchdown"] or {}).get(key)


CONNECTORS = {
    "lm.time.sim": Point(lambda s: round(s["tick"] / 10.0, 1), doc="Simulated seconds since boot"),
    "lm.time.met": Point(_met, doc="Mission elapsed time, h:mm:ss"),
    "lm.lgc.program": Point(lambda s: s["lgc"]["program"], doc="The major mode (63, 64, ...)"),
    "lm.lgc.alarms": Point(lambda s: edn.Vector(s["lgc"]["alarms"]),
                           doc="Every program alarm code so far, in order"),
    "lm.lgc.restarts": Point(lambda s: s["lgc"]["restarts"], doc="Software restarts so far"),
    "lm.lgc.load": Point(lambda s: s["lgc"]["load_fraction"],
                         doc="The executive's load, a fraction of its capacity"),
    "lm.lgc.prop-percent": Point(lambda s: round(L.prop_percent(s), 1),
                                 doc="Descent propellant remaining, as the LGC computes it (N93)"),
    "lm.lgc.lr-enabled": Point(lambda s: s["lgc"]["lr_incorporate"],
                               doc="Whether the crew has enabled the landing radar (V57)"),
    "lm.lgc.rate-command": Point(
        lambda s: None if s["lgc"]["vz_cmd"] is None else round(s["lgc"]["vz_cmd"], 4),
        doc="The rate of descent P65 or P66 holds, m/s (negative down)"),
    "lm.lgc.config.mission": Point(lambda s: keyword(s["lgc"]["load"]),
                                   doc="The mission the erasable load is for"),
    "lm.lgc.config.vehicle": Point(lambda s: keyword(s["vehicle"]),
                                   doc="The vehicle the LM is"),
    "lm.dsky.verb": Point(lambda s: s["lgc"]["display"]["verb"]),
    "lm.dsky.noun": Point(lambda s: s["lgc"]["display"]["noun"]),
    "lm.dsky.r1": Point(lambda s: s["lgc"]["display"]["r"][0]),
    "lm.dsky.r2": Point(lambda s: s["lgc"]["display"]["r"][1]),
    "lm.dsky.r3": Point(lambda s: s["lgc"]["display"]["r"][2]),
    "lm.dsky.flashing": Point(lambda s: s["lgc"]["flashing"],
                              doc="Verb and noun flash: the computer waits for the crew"),
    "lm.nav.altitude": Point(lambda s: round(L.nav(s)["h"], 1), doc="Altitude, as the LGC knows it"),
    "lm.nav.altitude-rate": Point(lambda s: round(L.nav(s)["vz"], 2)),
    "lm.nav.delta-h": Point(lambda s: round(L.delta_h(s), 1),
                            doc="Radar altitude less computed altitude"),
    "lm.lr.alt-good": Point(lambda s: s["lr"]["alt_good"]),
    "lm.lr.vel-good": Point(lambda s: s["lr"]["vel_good"]),
    "lm.truth.altitude": Point(lambda s: round(s["h"], 1), doc="The real altitude"),
    "lm.truth.altitude-rate": Point(lambda s: round(s["vz"], 2)),
    "lm.truth.downrange": Point(lambda s: round(s["x"], 1),
                                doc="Distance from the landing site, negative before it"),
    "lm.truth.vx": Point(lambda s: round(s["vx"], 2)),
    "lm.deca.throttle": Point(lambda s: round(s["throttle"] * 100, 1), doc="Throttle, percent"),
    "lm.engine.descent.on": Point(lambda s: s["des_on"]),
    "lm.engine.ascent.on": Point(lambda s: s["asc_on"]),
    "lm.staged": Point(lambda s: s["staged"]),
    "lm.prop.descent-kg": Point(lambda s: round(s["prop_d"], 1)),
    "lm.prop.ascent-kg": Point(lambda s: round(s["prop_a"], 1)),
    "lm.prop.low-level": Point(V.descent_propellant_low,
                               doc="The descent tanks' low-level sensor"),
    "lm.cwea.master-alarm": Point(lambda s: s["cwea"]["master_alarm"]),
    "lm.cwea.caution": Point(V.has_caution, doc="Any caution light is lit"),
    "lm.cwea.warning": Point(V.has_warning, doc="Any warning light is lit"),
    "lm.eps.bus-volts": Point(lambda s: s["eps"]["volts"]),
    "lm.eps.amps": Point(lambda s: s["eps"]["amps"]),
    "lm.eps.ah": Point(lambda s: round(sum(b["ah"] for b in s["eps"]["batteries"]), 1),
                       doc="Amp-hours left in the descent batteries"),
    "lm.ecs.o2-kg": Point(lambda s: round(s["ecs"]["o2"], 2)),
    "lm.ecs.water-kg": Point(lambda s: round(s["ecs"]["water"], 1)),
    "lm.contact": Point(lambda s: s["contact"], doc="The lunar contact light"),
    "lm.landed": Point(lambda s: s["landed"]),
    "lm.touchdown.vz": Point(_touchdown("vz"), doc="Vertical velocity at touchdown, m/s"),
    "lm.touchdown.vx": Point(_touchdown("vx"), doc="Horizontal velocity at touchdown, m/s"),
    "lm.touchdown.miss-m": Point(_touchdown("miss"), doc="Distance from the landing site"),
    # The crew's panel
    "lm.panel.abort": Point(lambda s: s["panel"]["abort"], _panel("abort")),
    "lm.panel.abort-stage": Point(lambda s: s["panel"]["abort_stage"], _panel("abort_stage")),
    "lm.panel.engine-stop": Point(lambda s: s["panel"]["engine_stop"], _panel("engine_stop")),
    "lm.panel.master-arm": Point(lambda s: s["panel"]["master_arm"], _panel("master_arm")),
    "lm.panel.engine-arm": Point(lambda s: keyword(s["panel"]["engine_arm"]),
                                 _panel("engine_arm", str, ("off", "des", "asc"))),
    "lm.panel.rr-mode": Point(lambda s: keyword(s["panel"]["rr_mode"]),
                              _panel("rr_mode", str, ("lgc", "auto", "slew")),
                              doc="The rendezvous radar's mode switch"),
    # The bench: faults injected from the instructor station
    "lm.bench.lr-failed": Point(lambda s: s["bench"]["lr_failed"], _bench("lr_failed"),
                                released=False),
    "lm.bench.rr-cdu-fault": Point(lambda s: s["bench"]["rr_cdu_fault"], _bench("rr_cdu_fault"),
                                   doc="The rendezvous radar's angle counters run away "
                                       "(Apollo 11's 1202s)", released=False),
    "lm.bench.bus-load-amps": Point(lambda s: s["bench"]["bus_load_amps"],
                                    _bench("bus_load_amps", float),
                                    doc="Extra load on the bus", released=0.0),
    "lm.bench.o2-leak-kg-h": Point(lambda s: s["bench"]["o2_leak_kg_h"],
                                   _bench("o2_leak_kg_h", float), released=0.0),
}
for _name in L.LIGHTS:
    CONNECTORS[f"lm.dsky.light.{_name}"] = Point(_light(_name))
for _name in V.CAUTION_LIGHTS:
    CONNECTORS[f"lm.cwea.light.{_name}"] = Point(_caution(_name))
for _n in range(1, 6):
    CONNECTORS[f"lm.eps.battery.{_n}.ah"] = Point(
        lambda s, n=_n: round(s["eps"]["batteries"][n - 1]["ah"], 1)
        if n <= len(s["eps"]["batteries"]) else None)
    CONNECTORS[f"lm.bench.battery.{_n}.fault"] = Point(
        lambda s, n=_n: bool(s["bench"]["battery_faults"].get(str(n))),
        _battery_fault(_n), released=False)


def resolve(path):
    point = CONNECTORS.get(str(path))
    if point is None:
        raise KeyError(f"the lm has no connector {path}")
    return point


def read(s, path):
    return resolve(path).read(s)


def write(s, path, value):
    resolve(path).write(s, value)


def fix(s, path, value):
    """Hold an input at a value, every step"""
    point = resolve(path)
    point.write(s, value)
    s["fixed"][path] = value


def release(s, path):
    point = resolve(path)
    if point.write_fn is None:
        raise PermissionError("read-only")
    s["fixed"].pop(path, None)
    if point.released is not None:
        point.write(s, point.released)


def _apply(s, value, path):
    resolve(path).write(s, value)


for _path, _point in CONNECTORS.items():
    if _point.write_fn is not None:
        sim.register_fixer(_path, (lambda path: lambda s, value: _apply(s, value, path))(_path))


class Connector(Ref):
    """A point of the lunar module, its panel or the bench, by path
    (e.g. "lm.dsky.verb"). Scripts make one with (connector "path")."""

    @classmethod
    def children(cls, path):
        return children(path)


def children(path):
    """The refs.Childs directly below a connector path ("" for the top)"""
    prefix = f"{path}." if path else ""
    found = {}
    for full, point in CONNECTORS.items():
        if not full.startswith(prefix):
            continue
        child, _, rest = full[len(prefix):].partition(".")
        if rest:
            kind, count = found.get(child, ("branch", 0))
            if kind == "branch":
                found[child] = ("branch", count + 1)
        else:
            found[child] = ("leaf", point)
    out = []
    for child, (kind, what) in found.items():
        if kind == "leaf":
            out.append(Child(child, leaf=True,
                             detail="settable" if what.write_fn else "read-only", doc=what.doc))
        else:
            out.append(Child(child, detail=f"{what} connector{'s' if what > 1 else ''} below"))
    return out
