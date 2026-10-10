"""Blocks for testing the simulated Vehicle Manager

They reach the platform through the ``vm`` handle bound for each run.
Its points are Connectors, the VM's kind of ref: this plugin implements
Read, SetValue, SetFixedValue and ClearFixedValue for them, and Verify
and Wait read them through its Read.
"""

from automationv3.framework import context, edn, html, lisp
from automationv3.framework.block import ACTION, VALUE, BlockResult, BuildingBlock
from automationv3.framework.refs import Ref
from automationv3.plugins.core import value_blocks
from automationv3.framework.language import is_text

PACKET_OPTIONS = {"defect", "via", "at", "seq"}


def vm():
    return context.lookup("vm")


def show(value):
    return edn.writes(value)


class SendTC(BuildingBlock):
    """Send a telecommand to the Vehicle Manager and give back the result
    it reported for it.

    ``command`` is the command code; the rest are pairs of argument names
    and values. Four names describe the packet rather than the command:

    - ``:at`` time-tags it for that on-board time (seconds);
    - ``:via`` picks the transponder, ``:a`` (default) or ``:b``;
    - ``:seq`` sets its sequence number;
    - ``:defect`` spoils it on purpose: ``:crc``, ``:length``,
      ``:argument`` (puts an argument out of range) or
      ``:authentication``.

    The result is ``:executed``, ``:queued`` (time-tagged for later), or
    ``:rejected-...`` with the reason, e.g. ``:rejected-crc``. A rejection
    is a result, not a failure of the step: assert the result you expect.

    Examples::

        (Verify (SendTC :set-mode :mode :safe) = :executed)
        (SendTC :noop :at (+ (Telemetry :time) 600))
        (SendTC :noop :defect :crc :via :b)
    """

    kind = ACTION

    def usage(self):
        return "(SendTC command name value ...)"

    def check_syntax(self, *args):
        return len(args) % 2 == 1 and isinstance(args[0], (edn.Symbol, list))

    def execute(self, command, *pairs):
        fields = dict(zip(pairs[::2], pairs[1::2]))
        packet = {k: v for k, v in fields.items() if edn.writes(k)[1:] in PACKET_OPTIONS}
        args = {k: v for k, v in fields.items() if edn.writes(k)[1:] not in PACKET_OPTIONS}
        if packet.get(edn.Keyword("defect")) == edn.Keyword("argument"):
            args[edn.Keyword("pad")] = 300  # outside every range
            del packet[edn.Keyword("defect")]
        result = vm().telecommand(command, args, packet)
        sent = " ".join(show(x) for x in (command, *pairs))
        return BlockResult(True, value=result, stdout=f"{sent} -> {show(result)}")

    def as_html(self, command, *pairs):
        rest = " ".join(html.text(x) for x in pairs)
        return (f'<span><strong>Send telecommand</strong> '
                f'<span class="ui-mono">{html.text(command)} {rest}</span></span>')


class Telemetry(BuildingBlock):
    """The current value of a Vehicle Manager telemetry parameter.

    Parameters: ``:mode``, ``:time``, ``:noop-count``, ``:reset-cause``,
    ``:attitude-mode``, ``:soc``, ``:charge-current``,
    ``:max-charge-current``, ``:shed``, ``:tt-queue-count``,
    ``:tt-suspended``, ``:safe-discrete``, ``:last-event``,
    ``:last-report-latency``; and ``:line`` with a power line's name, for
    its state as a map (``:on``, ``:tripped``, ``:switch_ms``).

    Examples::

        (Verify (Telemetry :mode) = :safe)
        (Verify (.get (Telemetry :line :payload) :on) = false)
    """

    kind = VALUE

    def usage(self):
        return "(Telemetry parameter)\n(Telemetry :line name)"

    def check_syntax(self, *args):
        return len(args) in (1, 2) and isinstance(args[0], edn.Keyword)

    def execute(self, parameter, detail=None):
        return vm().telemetry(parameter, detail)


class RunFor(BuildingBlock):
    """Let simulated time run for a number of seconds.

    Example::

        (RunFor 60)
    """

    kind = ACTION

    def check_syntax(self, *args):
        return len(args) == 1

    def execute(self, seconds):
        now = vm().run_for(seconds)
        return BlockResult(True, stdout=f"ran {show(seconds)} s; on-board time {now:g} s")

    def as_html(self, seconds):
        return f"<span><strong>Run for</strong> {html.text(seconds)} s</span>"


class BringToMode(BuildingBlock):
    """Bring the platform to a mode through the transitions it allows,
    commanding each in turn (and waiting out LAUNCH's minimum time).
    ``:launch`` replays separation instead.

    Example::

        (BringToMode :maneuver)
    """

    kind = ACTION

    def check_syntax(self, *args):
        return len(args) == 1

    def execute(self, mode):
        path = vm().bring_to(mode)
        steps = " then ".join(show(m) for m in path) or "nothing to do"
        return BlockResult(True, stdout=f"commanded {steps}")


# Connectors: the VM's kind of ref, and the blocks that reach them


class Connector(Ref):
    """A point of the Vehicle Manager or its bench, by path
    (e.g. "vm.eps.soc"). Scripts make one with (connector "path")."""


def make_connector(path):
    """(connector "vm.eps"): a connector of the Vehicle Manager"""
    return Connector(path)


lisp.global_env["connector"] = make_connector


def point(call, ref, *args):
    try:
        return call(ref.path, *args)
    except KeyError as e:
        raise LookupError(f"{ref.label}: {e.args[0]}") from None


class Read(value_blocks.Read):
    """Reads a Vehicle Manager connector"""

    ref_type = Connector

    def read(self, ref):
        return point(vm().read_point, ref)


class SetValue(value_blocks.SetValue):
    """Writes a Vehicle Manager bench input"""

    ref_type = Connector

    def write(self, ref, value):
        point(vm().set_point, ref, value)


class SetFixedValue(value_blocks.SetFixedValue):
    """Holds a Vehicle Manager bench input, every frame"""

    ref_type = Connector

    def fix(self, ref, value):
        point(vm().fix_point, ref, value)


class ClearFixedValue(value_blocks.ClearFixedValue):
    """Releases a Vehicle Manager bench input"""

    ref_type = Connector

    def release(self, ref):
        point(vm().release_point, ref)
