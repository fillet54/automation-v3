"""The Apollo lunar module: the sample unit under test

A small simulation of the lunar module's powered descent and its
guidance computer (the LGC, running a Luminary rope), from powered
descent initiation to the surface: the ``lm`` UUT, in the ``sim`` and
``lms`` environments, with the blocks its tests use. The model lives in
``model/`` and knows nothing of automationv3; the example scripts and
requirements that test it are in ``automationv3/examples/apollo``.
"""

from .blocks import (
    AttachTrajectory, ClearFixedValue, ClickROD, Connector, FlyTo, Keys, Proceed,
    PushMasterAlarm, Read, RunFor, SetFixedValue, SetValue, StartLM, make_connector,
)
from . import documents
from .environments import Lms, Sim
from .uut import LunarModule

__all__ = ["AttachTrajectory", "ClearFixedValue", "ClickROD", "Connector", "FlyTo",
           "Keys", "Proceed", "PushMasterAlarm", "Read", "RunFor", "SetFixedValue",
           "SetValue", "StartLM", "Lms", "Sim", "LunarModule"]


def register(registry):
    registry.function("connector", make_connector)
    registry.function("lm/connector", make_connector)
    documents.register(registry)
