"""The Vehicle Manager sample: a simulated satellite platform's flight
software, and the blocks its tests use

The ``vm`` UUT runs in the sample ``sim`` and ``bench`` environments.
See ``sim.py`` for what it simulates.
"""

from .blocks import (
    BringToMode, ClearFixedValue, Connector, Read, RunFor, SendTC, SetFixedValue, SetValue,
    Telemetry,
)
from .sim import VehicleManager

__all__ = [BringToMode, ClearFixedValue, Connector, Read, RunFor, SendTC, SetFixedValue,
           SetValue, Telemetry, VehicleManager]


def register(registry):
    from .blocks import make_connector
    registry.function("connector", make_connector)
    registry.function("vm/connector", make_connector)
