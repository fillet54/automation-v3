"""Connectors: the signals a UUT exposes, as values scripts pass around

A connector is a reference to one point of a UUT, by its path, e.g.
"sys.cpu1.app.nav.mode". Scripts make one with `connector` and reach
the points below it with dotted names::

    (def cpu1 (connector "sys.cpu1"))
    (Verify cpu1.app.nav.mode = :run)    ; sys.cpu1.app.nav.mode

Anything bound to a connector can be extended that way: a def, a defn
parameter, a table row symbol. `(def nav cpu1.app.nav)` gives a deep
path a short name. A connector is named by the def that binds it, and
reports show that name, e.g. nav.mode, with the full path beside it.

A group is several connectors tested together, e.g. redundant units::

    (def cpu (group cpu1 cpu2))
    (Verify cpu.app.nav.mode = :run)     ; both cpu1's and cpu2's

`cpu.app.nav.mode` is the group of each member's path. Members keep
their own names (cpu1, cpu2); reading a group gives a map of member
name (a keyword, :cpu1) to value.

Reading and writing go through blocks (Read, SetValue, SetFixedValue,
ClearFixedValue, and the Verify and Wait families), which reach the UUT
through its handle. A handle that serves connectors has these methods:

- read_connector(path) -> value
- set_connector(path, value)
- fix_connector(path, value): hold the value until cleared
- clear_connector(path): release a held value
- connector_clock() -> seconds, and connector_sleep(seconds), optional:
  the UUT's time, for UUTs (e.g. simulations) whose time isn't the
  wall clock's.

Every access is recorded: each statement reports the connector paths it
touched and how (read, set, fix, clear) as `connector` events.
"""

import time

from . import context, edn, lisp

OPERATIONS = ("read", "set", "fix", "clear")


class Connector:
    """A reference to one point of a UUT, by path"""

    __slots__ = ("path", "name", "uut")

    def __init__(self, path, name=None, uut=None):
        if not isinstance(path, str) or not path or isinstance(path, edn.Keyword):
            raise TypeError(f"connector takes a path, as a string: (connector \"a.b\"), "
                            f"not {edn.writes(path)}")
        self.path, self.name, self.uut = str(path), name, uut

    def __child__(self, rest):
        name = f"{self.name}.{rest}" if self.name else None
        return Connector(f"{self.path}.{rest}", name, self.uut)

    def __named__(self, name):
        return Connector(self.path, name, self.uut)

    @property
    def label(self):
        """How reports name it: as the script does, or by path"""
        return self.name or self.path

    def __eq__(self, other):
        return isinstance(other, Connector) and (self.path, self.uut) == \
            (other.path, other.uut)

    def __hash__(self):
        return hash((self.path, self.uut))

    def __repr__(self):
        return self.label


class Group:
    """Connectors tested together: [(member name, Connector)]"""

    __slots__ = ("members", "name")

    def __init__(self, members, name=None):
        self.members = list(members)
        self.name = name

    def __child__(self, rest):
        name = f"{self.name}.{rest}" if self.name else None
        return Group([(member, c.__child__(rest)) for member, c in self.members], name)

    def __named__(self, name):
        return Group(self.members, name)

    @property
    def label(self):
        return self.name or "(group " + " ".join(c.label for _, c in self.members) + ")"

    def __len__(self):
        return len(self.members)

    def __eq__(self, other):
        return isinstance(other, Group) and self.members == other.members

    def __hash__(self):
        return hash(tuple(c for _, c in self.members))

    def __repr__(self):
        return self.label


def is_connector(value):
    return isinstance(value, (Connector, Group))


def make_connector(path, uut=None):
    """(connector "path") or (connector "path" :uut-name): a reference to
    a point of the UUT. With one UUT serving connectors, it needn't be
    named."""
    return Connector(path, uut=str(uut).lstrip(":") if uut is not None else None)


def make_group(*members):
    """(group a b ...): connectors (or groups, whose members join) tested
    together"""
    found = []
    for member in members:
        if isinstance(member, Group):
            found.extend(member.members)
        elif isinstance(member, Connector):
            found.append((member.label, member))
        else:
            raise TypeError(f"group takes connectors, not {edn.writes(member)}")
    if not found:
        raise TypeError("group takes at least one connector")
    names = [name for name, _ in found]
    if len(set(names)) != len(names):
        raise TypeError(f"a group's members need different names: {' '.join(names)}")
    return Group(found)


def members(value):
    """[(name, Connector)] of a connector or group"""
    if isinstance(value, Group):
        return value.members
    return [(value.label, value)]


# Reaching the UUT


def _bound_values(env):
    while env is not None:
        yield from dict.values(env)
        env = getattr(env, "outer", None)


def sources(env=None):
    """The handles in the running script that serve connectors"""
    env = env if env is not None else context.current_env()
    seen = []
    for value in _bound_values(env):
        if hasattr(value, "read_connector") and not any(value is s for s in seen):
            seen.append(value)
    return seen


def source_of(connector):
    """The handle serving `connector`"""
    env = context.current_env()
    if connector.uut is not None:
        handle = env[edn.Symbol(connector.uut)]
        if not hasattr(handle, "read_connector"):
            raise TypeError(f"{connector.uut} doesn't serve connectors")
        return handle
    found = sources(env)
    if not found:
        raise RuntimeError(f"no UUT serves connectors, for {connector.label}: "
                           "declare one with (uut :name)")
    if len(found) > 1:
        raise RuntimeError(f"several UUTs serve connectors: name the one "
                           f"{connector.label} is on, (connector \"...\" :uut)")
    return found[0]


def record(connector, operation):
    """Report that the running statement touched `connector`"""
    from .steps import _runtime
    runtime = _runtime.get()
    if runtime is None:
        return
    runtime.touch(connector, operation)


def read(value):
    """The value at a connector; for a group, {:member-name value}"""
    if isinstance(value, Group):
        return edn.Map({edn.Keyword(name): read(c) for name, c in value.members})
    if not isinstance(value, Connector):
        raise TypeError(f"{edn.writes(value)} isn't a connector")
    record(value, "read")
    return source_of(value).read_connector(value.path)


def value_of(value):
    """A connector's value; anything else as it is"""
    return read(value) if isinstance(value, Connector) else value


def write(value, new, operation="set"):
    """Set (or fix, or clear) every connector in `value`"""
    if not is_connector(value):
        raise TypeError(f"{edn.writes(value)} isn't a connector")
    for _, c in members(value):
        record(c, operation)
        handle = source_of(c)
        if operation == "set":
            handle.set_connector(c.path, new)
        elif operation == "fix":
            handle.fix_connector(c.path, new)
        else:
            handle.clear_connector(c.path)


def same(value):
    """(same? group): true if every member reads the same"""
    if not is_connector(value):
        raise TypeError(f"same? takes a connector group, not {edn.writes(value)}")
    values = [read(c) for _, c in members(value)]
    return all(v == values[0] for v in values[1:])


# Time: the UUT's, when it keeps its own


class WallClock:
    """Time when no UUT keeps its own"""

    def now(self):
        return time.monotonic()

    def sleep(self, seconds):
        time.sleep(seconds)


wall_clock = WallClock()  # tests swap in one that doesn't really wait


def _clock_source():
    try:
        found = [s for s in sources() if hasattr(s, "connector_clock")]
    except RuntimeError:
        return None
    return found[0] if found else None


def clock():
    """Seconds, by the UUT's clock if it keeps one"""
    source = _clock_source()
    return source.connector_clock() if source else wall_clock.now()


def sleep(seconds):
    """Let `seconds` pass, by the UUT's clock if it keeps one"""
    source = _clock_source()
    if source:
        source.connector_sleep(seconds)
    else:
        wall_clock.sleep(seconds)


lisp.global_env.update({
    "connector": make_connector,
    "group": make_group,
    "same?": same,
    "connector?": is_connector,
})
