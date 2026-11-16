"""How long resolving every closure in the demo takes

For plans/source-tree.md: run before step 2 and after it, and write both
numbers in the plan's notes. Deleted with test/baseline.py in step 7.

    python -m test.bench_closures [--sweeps N]

Resolves every script (not core.rst) in each of the demo's workspaces,
analysis included, as planning a report does. The first sweep is cold
(nothing parsed yet in this process); the best of the rest shows what
caching gives. Needs the demo: `automation-v3 demo` makes it.
"""

import argparse
import sys
import time
from pathlib import Path

from automationv3.framework import closure, source

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo" / "workspace"


def scripts():
    """[(root, script)] for every script in the demo's workspaces"""
    found = []
    for workspace in sorted(DEMO.iterdir()):
        root = workspace / "rvts"
        for path in sorted(root.rglob("*.rst")):
            if path.name != "core.rst" and source.has_rvt(path.read_text()):
                found.append((root, str(path.relative_to(root))))
    return found


def sweep(found):
    start = time.perf_counter()
    for root, script in found:
        closure.resolve(root, script)
    return time.perf_counter() - start


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sweeps", type=int, default=5)
    args = parser.parse_args()
    if not DEMO.is_dir():
        sys.exit(f"no demo at {DEMO}: run `automation-v3 demo` first")
    found = scripts()
    times = [sweep(found) for _ in range(args.sweeps)]
    print(f"{len(found)} closures: cold {times[0] * 1000:.0f} ms, "
          f"best of {len(times) - 1} warm {min(times[1:]) * 1000:.0f} ms "
          f"({min(times[1:]) / len(found) * 1000:.1f} ms each)")


if __name__ == "__main__":
    main()
