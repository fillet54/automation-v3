"""Sample plugins: a simulated environment and a stub UUT

They exercise the UUT/Environment plumbing without real hardware. The
`sim` environment keeps its state in a work directory; the `demo` UUT
"installs" by recording the version there.
"""

from .blocks import StartDemo
from .demo import Bench, Demo, Sim

__all__ = [Bench, Demo, Sim, StartDemo]
