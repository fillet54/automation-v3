"""Blocks that read and write connectors (see framework/connectors.py)"""

from automationv3.framework import connectors, context, edn
from automationv3.framework.block import ACTION, VALUE, BlockResult, BuildingBlock
from automationv3.framework.connectors import is_connector, members


def show(value):
    return edn.writes(value)


def check_connector(value, block):
    if not is_connector(value):
        raise TypeError(f"{block} takes a connector, not {show(value)}")


class Read(BuildingBlock):
    """The value at a connector; for a group, a map of each member's name
    (as a keyword) to its value.

    Examples::

        (Read nav.mode)                 ; :run
        (Read cpu.nav.mode)             ; {:cpu1 :run, :cpu2 :run}
    """

    kind = VALUE

    def usage(self):
        return "(Read connector)"

    def check_syntax(self, *args):
        return len(args) == 1

    def execute(self, connector):
        check_connector(connector, "Read")
        value = connectors.read(connector)
        return BlockResult(True, stdout=f"{connector.label} is {show(value)}", value=value)


class SetValue(BuildingBlock):
    """Write a value to a connector (every member, for a group), once.
    The UUT may change it again afterwards; to hold it, use SetFixedValue.

    Example::

        (SetValue bench.sun false)
    """

    kind = ACTION

    def usage(self):
        return "(SetValue connector value)"

    def check_syntax(self, *args):
        return len(args) == 2

    def execute(self, connector, value):
        check_connector(connector, "SetValue")
        connectors.write(connector, value, "set")
        return BlockResult(True, stdout=f"{connector.label} set to {show(value)}")


def cleanup_key(connector):
    return ("fixed", connector.uut, connector.path)


class SetFixedValue(BuildingBlock):
    """Hold a connector (every member, for a group) at a value until
    ClearFixedValue releases it. Whatever the script doesn't release is
    released when the script ends, pass or fail.

    Example::

        (SetFixedValue aocs.attitude-error 15.0)
    """

    kind = ACTION

    def usage(self):
        return "(SetFixedValue connector value)"

    def check_syntax(self, *args):
        return len(args) == 2

    def execute(self, connector, value):
        check_connector(connector, "SetFixedValue")
        connectors.write(connector, value, "fix")
        for _, member in members(connector):
            context.add_cleanup(
                cleanup_key(member), f"ClearFixedValue {member.label}",
                lambda member=member: connectors.write(member, None, "clear"))
        return BlockResult(True, stdout=f"{connector.label} fixed at {show(value)}")


class ClearFixedValue(BuildingBlock):
    """Release a connector (every member, for a group) held by
    SetFixedValue.

    Example::

        (ClearFixedValue aocs.attitude-error)
    """

    kind = ACTION

    def usage(self):
        return "(ClearFixedValue connector)"

    def check_syntax(self, *args):
        return len(args) == 1

    def execute(self, connector):
        check_connector(connector, "ClearFixedValue")
        connectors.write(connector, None, "clear")
        for _, member in members(connector):
            context.drop_cleanup(cleanup_key(member))
        return BlockResult(True, stdout=f"{connector.label} released")
