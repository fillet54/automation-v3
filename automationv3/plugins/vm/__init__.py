"""The Vehicle Manager sample: a simulated satellite platform's flight
software, and the blocks its tests use

The ``vm`` UUT runs in the sample ``sim`` and ``bench`` environments.
See ``sim.py`` for what it simulates.
"""

from .blocks import BringToMode, RunFor, SendTC, Telemetry
from .sim import VehicleManager

__all__ = [BringToMode, RunFor, SendTC, Telemetry, VehicleManager]
