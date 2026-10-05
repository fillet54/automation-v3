"""The package layers only depend downwards.

    framework  language and execution: no storage, no HTTP, no Flask
    services   storage and processes: no Flask, no web
    web        Flask adapters over services and framework
    cli        entry points
    plugins    BuildingBlocks, UUTs, environments: framework only
"""

import ast
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "automationv3"

FORBIDDEN = {
    "framework": {
        "automationv3.services", "automationv3.web", "automationv3.cli",
        "flask", "sqlite3", "requests", "waitress",
    },
    "services": {"automationv3.web", "automationv3.cli", "flask", "waitress"},
    "plugins": {"automationv3.services", "automationv3.web", "automationv3.cli",
                "flask"},
}


def imported_modules(path):
    """Absolute names of every module `path` imports"""
    module = ".".join(path.relative_to(PACKAGE.parent).with_suffix("").parts)
    package = module if path.name == "__init__.py" else module.rsplit(".", 1)[0]
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                base = base[: len(base) - node.level + 1]
                name = ".".join(base + ([node.module] if node.module else []))
            else:
                name = node.module
            yield name
            for alias in node.names:  # from . import x may name a module
                yield f"{name}.{alias.name}"


class TestLayers(unittest.TestCase):
    def test_layers_only_depend_downwards(self):
        violations = []
        for layer, forbidden in FORBIDDEN.items():
            for path in sorted((PACKAGE / layer).rglob("*.py")):
                for name in imported_modules(path):
                    for banned in forbidden:
                        if name == banned or name.startswith(banned + "."):
                            violations.append(
                                f"{path.relative_to(PACKAGE)} imports {name}")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
