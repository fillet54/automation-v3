"""Generic test helpers added to the default Lisp by the core plugin."""

from automationv3.framework.refs import is_ref, make_group, same


def register(registry):
    registry.function("group", make_group)
    registry.function("same?", same)
    registry.function("ref?", is_ref)
