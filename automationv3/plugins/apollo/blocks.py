"""Blocks for flying the lunar module

They reach the LM through the ``lm`` handle bound for each run. Its
points are Connectors, the LM's kind of ref: this plugin implements
Read, SetValue, SetFixedValue and ClearFixedValue for them, and Verify
and Wait read them through its Read.
"""

import csv
import io

from automationv3.framework import context, edn, markup, refs, value_blocks
from automationv3.framework.block import ACTION, BlockResult, BuildingBlock
from automationv3.framework.refs import Ref
from automationv3.framework.steps import attach

from . import connectors
from .handle import PHASES
from .model import sim
from .plot import trajectory_svg

KEY_NAMES = {"V": "VERB", "N": "NOUN", "E": "ENTR", "P": "PRO", "R": "RSET",
             "K": "KEY REL", "C": "CLR", "+": "+", "-": "−"}


def lm():
    return context.lookup("lm")


def show(value):
    return edn.writes(value)


class StartLM(BuildingBlock):
    """Boot the lunar module from a configuration map.

    ``:mission`` is ``:standard`` or ``:extended`` (the erasable load);
    ``:vehicle`` the same, for the hardware, if it differs from the
    load; ``:start`` is where the flight begins: ``:pdi`` (powered
    descent initiation, the default), ``:high-gate``, ``:low-gate`` or
    ``:surface``; ``:crew`` is ``:nominal`` (flies the procedure),
    ``:hands-off`` (PRO and V57 only) or ``:manual`` (the script is the
    crew); ``:seed`` adds sensor noise (0: none).

    Fails if the installed rope won't take the load (LUM099 has no
    extended missions). In a rendered script the configuration reads as
    a table.

    Example::

        (StartLM {:mission :extended :start :high-gate})
    """

    kind = ACTION

    def usage(self):
        return "(StartLM {:mission m :start s :crew c :seed n})"

    def check_syntax(self, *args):
        return len(args) == 1 and isinstance(args[0], dict)

    def execute(self, config):
        try:
            result = lm().boot(config)
        except (ValueError, sim.StartUnreachable) as e:
            return BlockResult(False, stderr=str(e))
        if result == edn.Keyword("rejected-load"):
            return BlockResult(False, value=result,
                               stdout=f"{lm().version()} rejected the erasable load")
        settings = ", ".join(f"{show(k)} {show(v)}" for k, v in lm().config().items())
        return BlockResult(True, value=result, stdout=f"booted: {settings}")

    def as_rst(self, config):
        return markup.strong("Boot the lunar module") + "\n\n" + markup.mapping(
            config, caption="Configuration")


class Keys(BuildingBlock):
    """Key the DSKY and give back what it shows afterwards: a map of
    ``:verb``, ``:noun``, ``:r1``, ``:r2``, ``:r3`` and ``:flashing``.

    Keys are ``V`` (VERB), ``N`` (NOUN), digits, ``+``, ``-``, ``E``
    (ENTR), ``P`` (PRO), ``R`` (RSET), ``K`` (KEY REL) and ``C`` (CLR).
    Spaces are ignored. An entry the computer doesn't accept lights OPR
    ERR; that is a result to check, not a failure of the step.

    Examples::

        (Keys "V16N68E")
        (Verify (.get (Keys "V37E70E") :verb) = 6)
    """

    kind = ACTION

    def usage(self):
        return '(Keys "V16N68E")'

    def check_syntax(self, *args):
        return len(args) == 1 and isinstance(args[0], str)

    def execute(self, text):
        bad = set(str(text).upper().replace(" ", "")) - set("VN0123456789+-EPRKC")
        if bad:
            return BlockResult(False, stderr=f"no DSKY key {''.join(sorted(bad))}")
        shown = lm().keys(text)
        return BlockResult(True, value=shown, stdout=f"{text} -> {show(shown)}")

    def as_rst(self, text):
        caps = [KEY_NAMES.get(k, k) for k in str(text).upper().replace(" ", "")]
        return markup.line(markup.strong("Key"), markup.code(" ".join(caps)))


class Proceed(BuildingBlock):
    """Press PRO on the DSKY: at ignition (V99 N62 flashing), the crew's
    consent to light the descent engine.

    Example::

        (Proceed)
    """

    kind = ACTION

    def check_syntax(self, *args):
        return not args

    def execute(self):
        lm().keys("P")
        return BlockResult(True, stdout="PRO")

    def as_rst(self):
        return markup.line(markup.strong("Proceed"), "(PRO)")


class ClickROD(BuildingBlock):
    """Click the rate-of-descent switch: up (positive) or down
    (negative). In P64 or P65 the first click selects P66; in P66 each
    click changes the commanded rate of descent by 1 ft/s. Fails if the
    switch does nothing now (not in P64, P65 or P66).

    Example::

        (ClickROD 3)
    """

    kind = ACTION

    def usage(self):
        return "(ClickROD clicks)"

    def check_syntax(self, *args):
        return len(args) == 1

    def execute(self, clicks):
        if not lm().click_rod(clicks):
            return BlockResult(False, stderr="the ROD switch does nothing outside P64, P65 and P66")
        rate = connectors.name(lm().read_point("lm.lgc.program"))
        return BlockResult(True, stdout=f"{show(clicks)} click(s); P{rate}")

    def as_rst(self, clicks):
        return markup.line(markup.strong("Click the ROD switch"), markup.text(clicks), "time(s)")


class RunFor(BuildingBlock):
    """Let the flight run for a number of seconds (in lms, wait for it).

    Example::

        (RunFor 60)
    """

    kind = ACTION

    def check_syntax(self, *args):
        return len(args) == 1

    def execute(self, seconds):
        now = lm().run_for(seconds)
        return BlockResult(True, stdout=f"ran {show(seconds)} s; flight time {now:g} s")

    def as_rst(self, seconds):
        return markup.line(markup.strong("Run for"), markup.text(seconds) + " s")


class FlyTo(BuildingBlock):
    """Let the flight run until it reaches a phase: ``:ignition``,
    ``:throttle-down``, ``:high-gate``, ``:low-gate``, ``:p66``,
    ``:contact`` or ``:touchdown``. Fails if it doesn't within
    ``:within`` seconds (1500 by default).

    Examples::

        (FlyTo :high-gate)
        (FlyTo :touchdown :within 900)
    """

    kind = ACTION

    def usage(self):
        return "(FlyTo phase [:within seconds])"

    def check_syntax(self, *args):
        return (len(args) in (1, 3) and isinstance(args[0], edn.Keyword)
                and (len(args) == 1 or args[1] == edn.Keyword("within")))

    def execute(self, phase, _within=None, limit=1500):
        if connectors.name(phase) not in PHASES:
            return BlockResult(False, stderr=f"no phase {show(phase)}: "
                               + ", ".join(f":{p}" for p in PHASES))
        if not lm().fly_to(phase, limit):
            return BlockResult(False, stderr=f"didn't reach {show(phase)} within {show(limit)} s")
        now = lm().read_point("lm.time.sim")
        return BlockResult(True, stdout=f"reached {show(phase)} at {now:g} s")

    def as_rst(self, phase, *rest):
        return markup.line(markup.strong("Fly to"), markup.code(phase))


class PushMasterAlarm(BuildingBlock):
    """Push the MASTER ALARM light to silence it. The caution or warning
    light stays lit while its cause lasts.

    Example::

        (PushMasterAlarm)
    """

    kind = ACTION

    def check_syntax(self, *args):
        return not args

    def execute(self):
        lm().push_master_alarm()
        return BlockResult(True, stdout="master alarm pushed")


class AttachTrajectory(BuildingBlock):
    """Attach the flight so far to the run: ``<label>.csv`` (one row a
    second: time, downrange, altitude, velocities, throttle, program,
    propellant) and ``<label>.svg``, a plot of the descent.

    Example::

        (AttachTrajectory "descent")
    """

    kind = ACTION

    def usage(self):
        return '(AttachTrajectory "label")'

    def check_syntax(self, *args):
        return len(args) == 1 and isinstance(args[0], str)

    def execute(self, label):
        rows = lm().trajectory_rows()
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["t_s", "downrange_m", "altitude_m", "vx_ms", "vz_ms", "throttle_pct",
                         "program", "propellant_kg"])
        writer.writerows(rows)
        attach(f"{label}.csv", out.getvalue())
        attach(f"{label}.svg", trajectory_svg(rows, title=label))
        return BlockResult(True, stdout=f"attached {label}.csv and {label}.svg ({len(rows)} rows)")

    def as_rst(self, label):
        return markup.line(markup.strong("Attach the trajectory"), "as",
                           markup.code(f"{markup.written(label)}.csv"), "and",
                           markup.code(f"{markup.written(label)}.svg"))


# Connectors: the LM's kind of ref, and the blocks that reach them


class Connector(Ref):
    """A point of the lunar module, its panel or the bench, by path
    (e.g. "lm.dsky.verb"). Scripts make one with (connector "path")."""

    @classmethod
    def children(cls, path):
        return connectors.children(path)


@refs.constructs(Connector)
def make_connector(path):
    """(connector "lm.dsky"): a connector of the lunar module"""
    return Connector(path)


def point(call, ref, *args):
    try:
        return call(ref.path, *args)
    except KeyError as e:
        raise LookupError(f"{ref.label}: {e.args[0]}") from None


class Read(value_blocks.Read):
    """Reads a lunar module connector"""

    ref_type = Connector

    def read(self, ref):
        return point(lm().read_point, ref)


class SetValue(value_blocks.SetValue):
    """Sets a panel switch or a bench input"""

    ref_type = Connector

    def write(self, ref, value):
        point(lm().set_point, ref, value)


class SetFixedValue(value_blocks.SetFixedValue):
    """Holds a panel switch or a bench input, every step"""

    ref_type = Connector

    def fix(self, ref, value):
        point(lm().fix_point, ref, value)


class ClearFixedValue(value_blocks.ClearFixedValue):
    """Releases a panel switch or a bench input"""

    ref_type = Connector

    def release(self, ref):
        point(lm().release_point, ref)
