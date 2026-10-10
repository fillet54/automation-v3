"""Refs: references to values somewhere else, as values scripts pass
around

A ref names a value a block can read or write, by a path, e.g.
"sys.cpu1.app.nav.mode". The framework doesn't say what a ref points
into: a plugin defines its own kind (a subclass of Ref) and the blocks
that reach it, and scripts reach everything below a ref with dotted
names::

    (def cpu1 (connector "sys.cpu1"))      ; a plugin's kind of ref
    (Verify cpu1.app.nav.mode = :run)      ; sys.cpu1.app.nav.mode

Anything bound to a ref can be extended that way: a def, a defn
parameter, a table row symbol. `(def nav cpu1.app.nav)` gives a deep
path a short name: a ref is named by the def that binds it, and reports
show that name, with the path beside it.

A group is several refs tested together, e.g. redundant units::

    (def cpu (group cpu1 cpu2))
    (Verify cpu.app.nav.mode = :run)       ; both cpu1's and cpu2's

`cpu.app.nav.mode` is the group of each member's path. Members keep
their own names (cpu1, cpu2); reading a group gives a map of member
name (a keyword, :cpu1) to value.

Reading and writing go through blocks: Read, SetValue, SetFixedValue
and ClearFixedValue (plugins/core/value_blocks.py) are abstract, and a
plugin implements each for its kind of ref. Verify and Wait read refs
through whichever Read accepts them. Every read and write is recorded:
each statement reports the refs it touched, and how (read, set, fix,
clear), as `ref` events.
"""

import copy

from . import edn, lisp

OPERATIONS = ("read", "set", "fix", "clear")


class Ref:
    """A reference to a value, by path. Plugins subclass it for the
    values their blocks reach."""

    def __init__(self, path, name=None):
        if not isinstance(path, str) or not path or isinstance(path, edn.Symbol):
            raise TypeError(f"a ref takes a path, as a string (\"a.b\"), "
                            f"not {edn.writes(path)}")
        self.path, self.name = str(path), name

    def __child__(self, rest):
        child = copy.copy(self)
        child.path = f"{self.path}.{rest}"
        child.name = f"{self.name}.{rest}" if self.name else None
        return child

    def __named__(self, name):
        named = copy.copy(self)
        named.name = name
        return named

    @property
    def label(self):
        """How reports name it: as the script does, or by path"""
        return self.name or self.path

    def __eq__(self, other):
        return type(other) is type(self) and other.path == self.path

    def __hash__(self):
        return hash((type(self).__name__, self.path))

    def __repr__(self):
        return self.label


class RefGroup:
    """Refs tested together: [(member name, Ref)]"""

    def __init__(self, members, name=None):
        self.members = list(members)
        self.name = name

    def __child__(self, rest):
        name = f"{self.name}.{rest}" if self.name else None
        return RefGroup([(member, r.__child__(rest)) for member, r in self.members], name)

    def __named__(self, name):
        return RefGroup(self.members, name)

    @property
    def label(self):
        return self.name or "(group " + " ".join(r.label for _, r in self.members) + ")"

    def __len__(self):
        return len(self.members)

    def __eq__(self, other):
        return isinstance(other, RefGroup) and self.members == other.members

    def __hash__(self):
        return hash(tuple(r for _, r in self.members))

    def __repr__(self):
        return self.label


def is_ref(value):
    """A ref or a group of them"""
    return isinstance(value, (Ref, RefGroup))


def members(value):
    """[(name, Ref)] of a ref or group"""
    if isinstance(value, RefGroup):
        return value.members
    return [(value.label, value)]


def accepts(ref_type, value):
    """True if `value` is a `ref_type` ref, or a group of only those"""
    if isinstance(value, RefGroup):
        return all(isinstance(r, ref_type) for _, r in value.members)
    return isinstance(value, ref_type)


def make_group(*refs):
    """(group a b ...): refs (or groups, whose members join) tested
    together"""
    found = []
    for ref in refs:
        if isinstance(ref, RefGroup):
            found.extend(ref.members)
        elif isinstance(ref, Ref):
            found.append((ref.label, ref))
        else:
            raise TypeError(f"group takes refs, not {edn.writes(ref)}")
    if not found:
        raise TypeError("group takes at least one ref")
    names = [name for name, _ in found]
    if len(set(names)) != len(names):
        raise TypeError(f"a group's members need different names: {' '.join(names)}")
    return RefGroup(found)


# Reaching values: through the blocks that implement them


def implementation(name, ref):
    """The one block named `name` that accepts `ref` (e.g. the Read for
    a plugin's kind of ref)"""
    from .block import AmbiguousBlock, NoBlock, _block_id, candidates
    found = [b for b in candidates(name) if b.check_syntax(ref)]
    if not found:
        raise NoBlock(f"no {name} accepts {ref.label}, a {type(ref).__name__}: "
                      "is the plugin that implements it loaded?")
    if len(found) > 1:
        raise AmbiguousBlock(
            f"{name} is accepted by {len(found)} blocks "
            f"({', '.join(_block_id(b) for b in found)}) for a {type(ref).__name__}")
    return found[0]


def record(ref, operation):
    """Report that the running statement touched `ref`"""
    from .steps import _runtime
    runtime = _runtime.get()
    if runtime is not None:
        runtime.touch(ref, operation)


def read(value, record_it=True):
    """The value a ref points at; for a group, {:member value}"""
    if isinstance(value, RefGroup):
        return edn.Map({edn.Keyword(name): read(r, record_it) for name, r in value.members})
    if not isinstance(value, Ref):
        raise TypeError(f"{edn.writes(value)} isn't a ref")
    if record_it:
        record(value, "read")
    return implementation("Read", value).read(value)


def same(value):
    """(same? group): true if every member reads the same"""
    if not is_ref(value):
        raise TypeError(f"same? takes a group of refs, not {edn.writes(value)}")
    values = [read(r) for _, r in members(value)]
    return all(v == values[0] for v in values[1:])


lisp.global_env.update({
    "group": make_group,
    "same?": same,
    "ref?": is_ref,
})
