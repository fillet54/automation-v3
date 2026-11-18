"""Where the lunar module runs: ``sim`` and ``lms``

``sim`` is software only: stepped and deterministic. Nothing happens
until a script runs time forward; Wait runs the LM forward as it polls.

``lms`` stands in for the Lunar Module Mission Simulator, the crew's
training simulator: the same model, paced against the wall clock
(``pace`` times real time, 20 by default), with terrain under the
approach that makes the landing radar drop out now and then, and DSKY
keys that take time to press. Time runs on its own there: every look at
the LM first catches the simulation up with the wall clock, so no
process has to run in the background.

Workers host them with a config like::

    {"environments": {"sim": {}, "lms": {"pace": 20}}}
"""

import platform
import tempfile
from pathlib import Path

from automationv3.framework.uut import Environment

from .model import missions as M

TERRAIN_MODEL = "1"


class Sim(Environment):
    """The lunar module in software, stepped"""

    name = "sim"

    def __init__(self, workdir=None, **params):
        super().__init__(workdir=workdir, **params)
        default = Path(tempfile.gettempdir()) / f"automationv3-{self.name}"
        self.workdir = Path(workdir or default)
        self.workdir.mkdir(parents=True, exist_ok=True)

    pace = None  # stepped

    def settings(self):
        """What this environment changes in a flight"""
        return {"terrain": False, "key_time": 0.0}

    def fingerprint(self):
        return {
            "environment": self.name,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "lm-model": M.MODEL_VERSION,
        }

    def clock(self, handles):
        """The LM's time, when it is under test (the wall clock if not)"""
        lm = handles.get("lm")
        return lm.clock() if lm is not None else None


class Lms(Sim):
    """The Lunar Module Mission Simulator: real time, sped up by `pace`"""

    name = "lms"

    def __init__(self, workdir=None, pace=20, **params):
        super().__init__(workdir=workdir, pace=pace, **params)
        self.pace = float(pace)

    def settings(self):
        return {"terrain": True, "key_time": 0.3}

    def fingerprint(self):
        return {**super().fingerprint(), "pace": self.pace, "terrain-model": TERRAIN_MODEL}
