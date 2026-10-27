"""The decision modules stay free of WizWalker, so they import and test anywhere, without the game."""

import ast
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "src" / "wizardtraining"
NO_GAME_ACCESS = ["config", "geometry", "routes", "targets", "policy", "progress", "state", "reports", "keys",
                  "language", "events", "teleports", "placed", "patrols", "knowledge", "motion", "gear", "connection",
                  "screen"]


def imported_modules(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names.add(node.module)
        elif isinstance(node, ast.ImportFrom):
            names.add("." + (node.module or ""))
    return names


class ImportBoundaryTest(unittest.TestCase):
    def test_decision_modules_import_no_game_library(self):
        for module in NO_GAME_ACCESS:
            for name in imported_modules(PACKAGE / f"{module}.py"):
                self.assertFalse(name.split(".")[0] == "wizwalker", f"{module} imports {name}")
                if name.startswith("."):
                    self.assertIn(name[1:], NO_GAME_ACCESS, f"{module} imports {name}")


if __name__ == "__main__":
    unittest.main()
