"""Read, SetValue, SetFixedValue and ClearFixedValue: abstract blocks
that reach the values refs point at (see framework/refs.py)

The framework doesn't know how to reach any value: a plugin implements
each block for its own kind of ref, by subclassing it, setting
`ref_type`, and implementing one method::

    class Read(value_blocks.Read):
        ref_type = Connector

        def read(self, ref):
            return my_system().read(ref.path)

The subclass keeps the block's name, usage and documentation, and
accepts a call only for its `ref_type` (or a group of only those), so
plugins with kinds of refs of their own can be loaded together; each of
these blocks requires that exactly one block accepts a call. The base
classes deal with groups (each member in turn), record the refs
touched, and release fixed values when the script ends.
"""

from automationv3.framework import context, edn, refs
from automationv3.framework.block import ACTION, VALUE, BlockResult, BuildingBlock
from automationv3.framework.refs import Ref, accepts, members


def show(value):
    return edn.writes(value)


class ValueBlock:
    """What the four blocks share: a ref as the first argument (a mixin,
    so it isn't a block of its own)"""

    require_unique = True
    ref_type = Ref  # the kind of ref an implementation reaches
    arguments = 1

    def check_syntax(self, *values):
        return len(values) == self.arguments and accepts(self.ref_type, values[0])


class Read(ValueBlock, BuildingBlock):
    """The value a ref points at; for a group, a map of each member's name
    (as a keyword) to its value.

    Implemented by plugins for their kinds of ref.

    Examples::

        (Read nav.mode)                 ; :run
        (Read cpu.nav.mode)             ; {:cpu1 :run, :cpu2 :run}
    """

    abstract = True
    kind = VALUE

    def usage(self):
        return "(Read ref)"

    def execute(self, ref):
        if isinstance(ref, Ref):
            refs.record(ref, "read")
            value = self.read(ref)
        else:
            value = edn.Map()
            for name, member in members(ref):
                refs.record(member, "read")
                value[edn.Keyword(name)] = self.read(member)
        return BlockResult(True, stdout=f"{ref.label} is {show(value)}", value=value)

    def read(self, ref):
        """The value at one ref (of `ref_type`)"""
        raise NotImplementedError


class SetValue(ValueBlock, BuildingBlock):
    """Write a value to a ref (every member, for a group), once. The
    system may change it again afterwards; to hold it, use SetFixedValue.

    Implemented by plugins for their kinds of ref.

    Example::

        (SetValue bench.sun false)
    """

    abstract = True
    kind = ACTION
    arguments = 2

    def usage(self):
        return "(SetValue ref value)"

    def execute(self, ref, value):
        for _, member in members(ref):
            refs.record(member, "set")
            self.write(member, value)
        return BlockResult(True, stdout=f"{ref.label} set to {show(value)}")

    def write(self, ref, value):
        """Write `value` to one ref"""
        raise NotImplementedError


def cleanup_key(ref):
    return ("fixed", type(ref).__name__, ref.path)


def release(ref):
    """Release one fixed ref, through the ClearFixedValue that accepts it"""
    refs.record(ref, "clear")
    refs.implementation("ClearFixedValue", ref).release(ref)


class SetFixedValue(ValueBlock, BuildingBlock):
    """Hold a ref (every member, for a group) at a value until
    ClearFixedValue releases it. Whatever the script doesn't release is
    released when the script ends, pass or fail.

    Implemented by plugins for their kinds of ref, along with
    ClearFixedValue.

    Example::

        (SetFixedValue aocs.attitude-error 15.0)
    """

    abstract = True
    kind = ACTION
    arguments = 2

    def usage(self):
        return "(SetFixedValue ref value)"

    def execute(self, ref, value):
        for _, member in members(ref):
            refs.record(member, "fix")
            self.fix(member, value)
            context.add_cleanup(cleanup_key(member), f"ClearFixedValue {member.label}",
                                lambda member=member: release(member))
        return BlockResult(True, stdout=f"{ref.label} fixed at {show(value)}")

    def fix(self, ref, value):
        """Hold one ref at `value`"""
        raise NotImplementedError


class ClearFixedValue(ValueBlock, BuildingBlock):
    """Release a ref (every member, for a group) held by SetFixedValue.

    Implemented by plugins for their kinds of ref.

    Example::

        (ClearFixedValue aocs.attitude-error)
    """

    abstract = True
    kind = ACTION

    def usage(self):
        return "(ClearFixedValue ref)"

    def execute(self, ref):
        for _, member in members(ref):
            refs.record(member, "clear")
            self.release(member)
            context.drop_cleanup(cleanup_key(member))
        return BlockResult(True, stdout=f"{ref.label} released")

    def release(self, ref):
        """Release one ref"""
        raise NotImplementedError
