"""Where the Apollo example lives: the scripts and the DOORS history that
`automation-v3 demo` is built from, and that tests use as real data"""

from pathlib import Path

EXAMPLE = Path(__file__).resolve().parent.parent / "automationv3" / "examples" / "apollo"
RVTS = EXAMPLE / "rvts"
DOORS = EXAMPLE / "doors"
