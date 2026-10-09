"""A simulated Vehicle Manager, for the VM sample tests

A small model of the satellite platform's flight software, enough for
the mode management, power and telecommand tests to run against: the
modes and their transitions, telecommand validation, time-tagged and
hazardous telecommands, battery state of charge, load shedding,
charging, power line switching and trips, and the FDIR triggers that
request SAFE mode.

Its state lives in the environment's work directory, so every run (and
every worker process) on that environment sees the same platform. Time
is simulated: nothing happens until a test runs time forward.

Scripts reach it through connectors too (see CONNECTORS below): its
telemetry points, read-only, and the bench's inputs (solar array,
battery, attitude error, line relays), which can be set, or fixed
until cleared. A fixed value is applied again every frame, so the
platform can't change it. Simulated time is the connectors' clock, so
Wait runs the platform forward while it polls.

Version 3.1.0 has a known defect: it restores loads shed for a low
state of charge by itself once the battery recovers past 65%, which
VM-EPS-003 forbids. 3.2.0 fixes it.
"""

import hashlib
import json

from automationv3.framework import edn
from automationv3.framework.uut import UUT, Version

MODES = ["launch", "safe", "standby", "nominal", "maneuver"]
ALLOWED = {
    "launch": ["safe"],
    "safe": ["standby"],
    "standby": ["nominal", "maneuver", "safe"],
    "nominal": ["standby", "safe"],
    "maneuver": ["standby", "safe"],
}
LAUNCH_MINIMUM_S = 30 * 60
ATTITUDE_MODE = {"launch": "sun-pointing", "safe": "sun-pointing",
                 "standby": "nadir-pointing", "nominal": "nadir-pointing",
                 "maneuver": "inertial"}

# Power lines; the essential ones are never shed
LINES = ["bus-computer", "receivers", "heater-essential", "transponder-a",
         "transponder-b", "star-tracker", "heater-non-essential", "payload"]
ESSENTIAL = {"bus-computer", "receivers", "heater-essential"}
TRIP_LIMIT_A = {line: 2.0 for line in LINES}
# State of charge thresholds and what is shed below each, in order
SHEDDING = [(60, "payload", ["payload"]),
            (50, "non-essential-heaters", ["heater-non-essential"]),
            (40, "all-but-essential", ["transponder-b", "star-tracker"])]
SAFE_SHEDS = ["payload", "heater-non-essential"]

BATTERY_AH = 40.0
CHARGE_LIMIT_A = BATTERY_AH / 5  # C/5
CHARGE_STOP_SOC = 95.0

# Telecommands: argument -> (low, high) for numbers, or allowed values
COMMANDS = {
    "noop": {"pad": (0, 255)},
    "set-mode": {"mode": MODES},
    "arm": {"command": None},
    "auth-enable": {"key": (0, 2**32 - 1)},
    "line-on": {"line": LINES},
    "line-off": {"line": LINES},
    "restore-loads": {},
    "tt-clear": {},
    "tt-resume": {},
    "propulsion-valve-open": {},
    "deployment-fire": {},
    "image-overwrite": {},
    "code-memory-patch": {},
}
HAZARDOUS = {"propulsion-valve-open", "deployment-fire", "image-overwrite",
             "code-memory-patch"}
ARM_WINDOW_S = 30
TIME_TAG_CAPACITY = 1000
STALE_TIME_TAG_S = 10
HISTORY = 500


def name(value):
    """'safe' for :safe or "safe" """
    return str(value).lstrip(":")


def keyword(value):
    return edn.Keyword(value) if value is not None else None


def fresh_state(installed=None):
    return {
        "installed": installed,
        "time": 0.0,
        "mode": "standby",
        "mode_since": 0.0,
        "safe_entered": None,
        "reset_cause": "power-on",
        "tc_task": True,
        "safe_discrete": False,
        "auth": None,
        "noop_count": 0,
        "reports": [],
        "events": [],
        "armed": {},
        "queue": [],
        "queue_suspended": False,
        "tt_lateness": [],
        "pulses": [],
        "lines": {line: {"on": True, "tripped": False, "switch_ms": 0}
                  for line in LINES},
        "shed": "none",
        "soc": 80.0,
        "discharge": None,  # [target soc, % per minute]
        "sun": False,
        "charge_current": 0.0,
        "max_charge_current": 0.0,
        "attitude_error": 0.0,
        "attitude_error_since": None,
        "soc_low_since": None,
        "fixed": {},  # connector path -> value held
        "subsecond": 0.0,  # simulated time short of the next frame
    }


class VehicleManager(UUT):
    """The simulated Vehicle Manager. Its handle is `vm`."""

    name = "vm"
    VERSIONS = ["3.1.0", "3.2.0"]

    def list_versions(self):
        return [Version(id, hashlib.sha256(f"vm-{id}".encode()).hexdigest())
                for id in self.VERSIONS]

    def path(self, env):
        return env.workdir / "vm-state.json"

    def load(self, env):
        path = self.path(env)
        if path.exists():
            return json.loads(path.read_text())
        return fresh_state()

    def save(self, env, state):
        self.path(env).write_text(json.dumps(state))

    def installed_version(self, env):
        installed = self.load(env)["installed"]
        return Version(**installed) if installed else None

    def install(self, version, env):
        if version not in self.list_versions():
            raise ValueError(f"vm has no version {version.id}")
        self.save(env, fresh_state({"id": version.id, "digest": version.digest}))

    def start(self, version, env):
        """Boot the platform fresh, in STANDBY"""
        self.save(env, fresh_state(self.load(env)["installed"]))

    def handle(self, version, env):
        return VehicleManagerHandle(self, env)


class Platform:
    """The VM's behaviour over one loaded state"""

    def __init__(self, state):
        self.s = state

    @property
    def version(self):
        return (self.s["installed"] or {}).get("id")

    # Records

    def event(self, kind, **detail):
        self.s["events"].append({"time": self.s["time"], "kind": kind, **detail})
        del self.s["events"][:-HISTORY]

    def report(self, code, result, seq=None):
        self.s["reports"].append({"time": self.s["time"], "code": code,
                                  "result": result, "seq": seq, "latency": 0.0})
        del self.s["reports"][:-HISTORY]
        if result.startswith("rejected"):
            self.event("tc-rejection", code=code, result=result)
        return result

    # Modes

    def enter(self, mode, why):
        previous = self.s["mode"]
        self.s["mode"] = mode
        self.s["mode_since"] = self.s["time"]
        self.event("mode-transition", previous=previous, mode=mode, why=why)
        if mode == "safe":
            for line in SAFE_SHEDS:
                self.s["lines"][line]["on"] = False
            self.s["queue_suspended"] = True
            self.s["safe_entered"] = self.s["time"]

    def request_safe(self, why):
        if self.s["mode"] not in ("launch", "safe"):
            self.event("fdir-safe-request", why=why)
            self.enter("safe", why)

    # Telecommands

    def validate(self, code, args, packet):
        if packet.get("defect") == "crc":
            return "rejected-crc"
        if packet.get("defect") == "length":
            return "rejected-length"
        if code not in COMMANDS:
            return "rejected-unknown"
        for arg, value in args.items():
            allowed = COMMANDS[code].get(arg, "missing")
            if allowed == "missing":
                return "rejected-range"
            if isinstance(allowed, tuple):
                if not (isinstance(value, (int, float))
                        and allowed[0] <= value <= allowed[1]):
                    return "rejected-range"
            elif isinstance(allowed, list) and name(value) not in allowed:
                return "rejected-range"
        if self.s["auth"] is not None and packet.get("defect") == "authentication":
            return "rejected-authentication"
        return None

    def telecommand(self, code, args, packet):
        """Validate and execute (or queue) one telecommand. Returns the
        result reported for it."""
        if not self.s["tc_task"]:
            return "lost"  # nothing processes it
        code = name(code)
        seq = packet.get("seq")
        rejected = self.validate(code, args, packet)
        if rejected:
            return self.report(code, rejected, seq)
        tag = packet.get("at")
        if tag is not None:
            if tag < self.s["time"] - STALE_TIME_TAG_S:
                return self.report(code, "rejected-stale", seq)
            if tag > self.s["time"]:
                if len(self.s["queue"]) >= TIME_TAG_CAPACITY:
                    return self.report(code, "rejected-queue-full", seq)
                self.s["queue"].append({"tag": tag, "code": code, "args": args})
                self.s["queue"].sort(key=lambda entry: entry["tag"])
                return self.report(code, "queued", seq)
        return self.report(code, self.execute(code, args), seq)

    def execute(self, code, args):
        s = self.s
        if code in HAZARDOUS:
            armed = s["armed"].pop(code, None)
            if armed is None or s["time"] - armed > ARM_WINDOW_S:
                return "rejected-not-armed"
            if code == "propulsion-valve-open" and s["mode"] != "maneuver":
                return "rejected-mode"
            s["pulses"].append({"code": code, "time": s["time"]})
            del s["pulses"][:-HISTORY]
            return "executed"
        if code == "noop":
            s["noop_count"] += 1
        elif code == "arm":
            s["armed"][name(args["command"])] = s["time"]
        elif code == "auth-enable":
            s["auth"] = args["key"]
        elif code == "set-mode":
            target = name(args["mode"])
            if target not in ALLOWED[s["mode"]]:
                return "rejected-transition"
            if s["mode"] == "launch" and s["time"] - s["mode_since"] < LAUNCH_MINIMUM_S:
                return "rejected-launch-minimum"
            self.enter(target, "commanded")
        elif code in ("line-on", "line-off"):
            line = s["lines"][name(args["line"])]
            line["on"] = code == "line-on"
            line["tripped"] = False if line["on"] else line["tripped"]
            line["switch_ms"] = 40
        elif code == "tt-clear":
            s["queue"] = []
        elif code == "tt-resume":
            s["queue_suspended"] = False
        elif code == "restore-loads":
            for _, _, lines in SHEDDING:
                for line in lines:
                    s["lines"][line]["on"] = True
            s["shed"] = "none"
        return "executed"

    # Time

    def tick(self):
        """One major frame (1 s)"""
        s = self.s
        s["time"] += 1.0
        self.apply_fixed()
        if s["tc_task"] and not s["queue_suspended"]:
            while s["queue"] and s["queue"][0]["tag"] <= s["time"]:
                entry = s["queue"].pop(0)
                s["tt_lateness"].append(s["time"] - entry["tag"])
                del s["tt_lateness"][:-2000]
                self.report(entry["code"], self.execute(entry["code"], entry["args"]))
        self.power()
        self.apply_fixed()
        self.fdir()

    def apply_fixed(self):
        """Hold every fixed connector at its value"""
        for path, value in self.s.get("fixed", {}).items():
            resolve(path).write(self, value)

    def power(self):
        s = self.s
        if s["discharge"]:
            target, per_minute = s["discharge"]
            s["soc"] = max(target, s["soc"] - per_minute / 60)
            if s["soc"] <= target:
                s["discharge"] = None
            s["charge_current"] = 0.0
        elif s["sun"] and s["soc"] < CHARGE_STOP_SOC:
            s["charge_current"] = CHARGE_LIMIT_A
            gained = 100 * CHARGE_LIMIT_A / 3600 / BATTERY_AH
            s["soc"] = min(CHARGE_STOP_SOC, s["soc"] + gained)
        else:
            s["charge_current"] = 0.0
        s["max_charge_current"] = max(s["max_charge_current"], s["charge_current"])
        for threshold, level, lines in SHEDDING:
            if s["soc"] < threshold and LEVELS.index(level) > LEVELS.index(s["shed"]):
                for line in lines:
                    s["lines"][line]["on"] = False
                s["shed"] = level
                self.event("load-shed", level=level)
        if self.version == "3.1.0" and s["shed"] != "none" and s["soc"] > 65:
            # The known defect: an autonomous restore
            for _, _, lines in SHEDDING:
                for line in lines:
                    s["lines"][line]["on"] = True
            s["shed"] = "none"

    def fdir(self):
        s = self.s
        if s["attitude_error"] > 10:
            s["attitude_error_since"] = s["attitude_error_since"] or s["time"]
            if s["time"] - s["attitude_error_since"] >= 60:
                self.request_safe("attitude-error")
        else:
            s["attitude_error_since"] = None
        if s["soc"] < 40:
            s["soc_low_since"] = s["soc_low_since"] or s["time"]
            if s["time"] - s["soc_low_since"] >= 10:
                self.request_safe("low-state-of-charge")
        else:
            s["soc_low_since"] = None


LEVELS = ["none", "payload", "non-essential-heaters", "all-but-essential"]


class VehicleManagerHandle:
    """What scripts see as `vm`: the platform's telemetry and telecommand
    link, and the test bench around it (battery and solar array
    simulators, fault injection, power supply)."""

    def __init__(self, uut, env):
        self.uut, self.env = uut, env

    def _run(self, change):
        state = self.uut.load(self.env)
        result = change(Platform(state))
        self.uut.save(self.env, state)
        return result

    def _read(self):
        return self.uut.load(self.env)

    # The link

    def telecommand(self, code, args, packet):
        args = {name(k): (name(v) if isinstance(v, edn.Keyword) else v)
                for k, v in (args or {}).items()}
        packet = {name(k): (name(v) if isinstance(v, edn.Keyword) else v)
                  for k, v in (packet or {}).items()}
        return keyword(self._run(lambda p: p.telecommand(code, args, packet)))

    def telemetry(self, parameter, detail=None):
        """The value of a telemetry parameter, as scripts see it"""
        s = self._read()
        parameter = name(parameter)
        if parameter == "line":
            line = s["lines"][name(detail)]
            return edn.Map({edn.Keyword(k): v for k, v in line.items()})
        values = {
            "mode": keyword(s["mode"]),
            "time": s["time"],
            "noop-count": s["noop_count"],
            "reset-cause": keyword(s["reset_cause"]),
            "attitude-mode": keyword(ATTITUDE_MODE[s["mode"]]),
            "soc": round(s["soc"], 3),
            "charge-current": s["charge_current"],
            "max-charge-current": s["max_charge_current"],
            "shed": keyword(s["shed"]),
            "tt-queue-count": len(s["queue"]),
            "tt-suspended": s["queue_suspended"],
            "safe-discrete": s["safe_discrete"],
            "last-event": keyword(s["events"][-1]["kind"]) if s["events"] else None,
            "last-report-latency": s["reports"][-1]["latency"] if s["reports"] else None,
        }
        if parameter not in values:
            raise KeyError(f"no telemetry parameter {parameter}")
        return values[parameter]

    def run_for(self, seconds):
        def run(platform):
            for _ in range(int(seconds)):
                platform.tick()
            return platform.s["time"]
        return self._run(run)

    def report_seqs(self, count):
        return [r["seq"] for r in self._read()["reports"][-count:]]

    def max_tt_lateness(self):
        return max(self._read()["tt_lateness"] or [0.0])

    def pulse_count(self, command):
        """How many times the actuator for a hazardous command has pulsed,
        as the bench's pulse counter on its drive line sees it"""
        return sum(p["code"] == name(command) for p in self._read()["pulses"])

    def had_event(self, kind, since):
        return any(e["kind"] == name(kind) and e["time"] >= since
                   for e in self._read()["events"])

    def safe_entry_delay(self):
        """Seconds from the SAFE request to the SAFE actions: the VM takes
        them in the frame it enters SAFE"""
        s = self._read()
        return 0.0 if s["safe_entered"] is not None else None

    # Connectors

    def read_connector(self, path):
        return resolve(path).read(self._read())

    def set_connector(self, path, value):
        point = resolve(path)
        value = name(value) if isinstance(value, edn.Keyword) else value

        def write(platform):
            try:
                point.write(platform, value)
            except PermissionError:
                raise PermissionError(f"{path} is read-only") from None
        self._run(write)

    def fix_connector(self, path, value):
        self.set_connector(path, value)
        value = name(value) if isinstance(value, edn.Keyword) else value

        def fix(platform):
            platform.s.setdefault("fixed", {})[str(path)] = value
        self._run(fix)

    def clear_connector(self, path):
        resolve(path)

        def clear(platform):
            platform.s.setdefault("fixed", {}).pop(str(path), None)
        self._run(clear)

    def connector_clock(self):
        s = self._read()
        return s["time"] + s.get("subsecond", 0.0)

    def connector_sleep(self, seconds):
        """Run simulated time forward, a frame at a time"""
        def run(platform):
            s = platform.s
            total = s.get("subsecond", 0.0) + float(seconds)
            frames = int(total + 1e-9)
            s["subsecond"] = max(0.0, total - frames)
            for _ in range(frames):
                platform.tick()
        self._run(run)

    # The bench

    def upload_noops(self, count, start_in, spacing):
        """A ground command load: `count` NO-OPs tagged `spacing` s apart,
        the first `start_in` s from now. Returns how many were queued."""
        def upload(platform):
            now = platform.s["time"]
            results = [platform.telecommand("noop", {}, {"at": now + start_in + i * spacing})
                       for i in range(count)]
            return results.count("queued")
        return self._run(upload)

    def separate(self):
        """Replay separation: the first boot after it, in LAUNCH"""
        def separate(platform):
            platform.enter("launch", "separation")
            platform.s["reset_cause"] = "power-on"
            return True
        return self._run(separate)

    def reset(self, cause):
        """Reset the bus computer (power cycle, watchdog, exception or
        commanded). The VM comes back in its mode, or SAFE after a
        watchdog or exception reset."""
        def reset(platform):
            s = platform.s
            cause_name = name(cause)
            s["reset_cause"] = cause_name
            s["tc_task"] = True
            if cause_name in ("watchdog", "exception") and s["mode"] != "launch":
                platform.enter("safe", "reset")
            platform.event("boot", cause=cause_name)
            return True
        return self._run(reset)

    def set_battery(self, soc):
        def set_battery(platform):
            platform.s["soc"] = float(soc)
            platform.s["discharge"] = None
            return True
        return self._run(set_battery)

    def discharge_to(self, soc, percent_per_minute):
        def discharge(platform):
            platform.s["discharge"] = [float(soc), float(percent_per_minute)]
            platform.s["sun"] = False
            return True
        return self._run(discharge)

    def set_sun(self, on):
        def sun(platform):
            platform.s["sun"] = bool(on)
            return True
        return self._run(sun)

    def overload(self, line, factor, duration_ms):
        """Draw `factor` times a line's trip limit for `duration_ms`"""
        def overload(platform):
            entry = platform.s["lines"][name(line)]
            if entry["on"] and factor > 1 and duration_ms > 10:
                entry["on"] = False
                entry["tripped"] = True
                platform.event("line-trip", line=name(line))
            return True
        return self._run(overload)

    def inject(self, fault, value):
        def inject(platform):
            if name(fault) == "attitude-error":
                platform.s["attitude_error"] = float(value)
            else:
                raise ValueError(f"no fault {fault}")
            return True
        return self._run(inject)

    def stop_tc_task(self):
        """The test hook that stops the VM's telecommand task"""
        def stop(platform):
            platform.s["tc_task"] = False
            return True
        return self._run(stop)

    def hw_command(self, command):
        """A hardware-decoded command: works without the VM's telecommand
        task"""
        command = name(command)
        if command == "safe":
            def safe(platform):
                platform.s["safe_discrete"] = True
                platform.request_safe("hardware-command")
                return True
            return self._run(safe)
        if command == "reset":
            return self.reset("commanded")
        raise ValueError(f"no hardware command {command}")

    def bring_to(self, mode):
        """Reach `mode` through allowed transitions, waiting out LAUNCH's
        minimum time when needed. Returns the modes passed through."""
        target = name(mode)

        def bring(platform):
            s = platform.s
            s["tc_task"] = True
            if target == "launch":
                platform.enter("launch", "separation")
                return [keyword("launch")]
            path = shortest_path(s["mode"], target)
            for step in path:
                if s["mode"] == "launch":
                    while s["time"] - s["mode_since"] < LAUNCH_MINIMUM_S:
                        platform.tick()
                result = platform.telecommand("set-mode", {"mode": step}, {})
                if result != "executed":
                    raise RuntimeError(f"{s['mode']} to {step} was {result}")
            return [keyword(step) for step in path]
        return self._run(bring)


# Connectors


class Point:
    """One connector of the platform: how to read it, and (for the
    bench's inputs) how to write it"""

    def __init__(self, read, write=None):
        self.read, self.write_fn = read, write

    def write(self, platform, value):
        if self.write_fn is None:
            raise PermissionError("read-only")
        self.write_fn(platform, value)


def _set(key, convert=lambda v: v):
    def write(platform, value):
        platform.s[key] = convert(value)
    return write


def _set_soc(platform, value):
    platform.s["soc"] = float(value)
    platform.s["discharge"] = None


def _line(line, field):
    def read(s):
        value = s["lines"][line][field]
        return value

    def write(platform, value):
        platform.s["lines"][line][field] = bool(value)

    return Point(read, write if field == "on" else None)


CONNECTORS = {
    "vm.obc.time": Point(lambda s: s["time"]),
    "vm.obc.reset-cause": Point(lambda s: keyword(s["reset_cause"])),
    "vm.mode.current": Point(lambda s: keyword(s["mode"])),
    "vm.mode.attitude": Point(lambda s: keyword(ATTITUDE_MODE[s["mode"]])),
    "vm.eps.soc": Point(lambda s: round(s["soc"], 3)),
    "vm.eps.charge-current": Point(lambda s: s["charge_current"]),
    "vm.eps.max-charge-current": Point(lambda s: s["max_charge_current"]),
    "vm.eps.shed": Point(lambda s: keyword(s["shed"])),
    "vm.tc.noop-count": Point(lambda s: s["noop_count"]),
    "vm.tc.tt-queue-count": Point(lambda s: len(s["queue"])),
    "vm.tc.tt-suspended": Point(lambda s: s["queue_suspended"]),
    "vm.fdir.safe-discrete": Point(lambda s: s["safe_discrete"]),
    "vm.fdir.last-event": Point(
        lambda s: keyword(s["events"][-1]["kind"]) if s["events"] else None),
    # The bench's inputs
    "vm.bench.sun": Point(lambda s: s["sun"], _set("sun", bool)),
    "vm.bench.battery.soc": Point(lambda s: round(s["soc"], 3), _set_soc),
    "vm.bench.attitude-error": Point(lambda s: s["attitude_error"],
                                     _set("attitude_error", float)),
}
for _line_name in LINES:
    for _field, _key in (("on", "on"), ("tripped", "tripped"), ("switch-ms", "switch_ms")):
        CONNECTORS[f"vm.eps.line.{_line_name}.{_field}"] = _line(_line_name, _key)


def resolve(path):
    """The Point at a connector path"""
    point = CONNECTORS.get(str(path))
    if point is None:
        raise KeyError(f"the vm has no connector {path}")
    return point


def shortest_path(start, target):
    """Modes to command, in order, to get from `start` to `target`"""
    frontier, seen = [(start, [])], {start}
    while frontier:
        mode, path = frontier.pop(0)
        if mode == target:
            return path
        for following in ALLOWED[mode]:
            if following not in seen:
                seen.add(following)
                frontier.append((following, path + [following]))
    raise ValueError(f"no way from {start} to {target}")
