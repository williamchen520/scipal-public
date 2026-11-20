from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.code_budget import collect


class CodeBudgetTest(unittest.TestCase):
    def test_counts_production_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "services").mkdir()
            (root / "services" / "a.py").write_text("a=1\nb=2\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_a.py").write_text("x=1\n", encoding="utf-8")
            (root / "scripts").mkdir()
            (root / "scripts" / "tool.py").write_text("x=1\n", encoding="utf-8")
            (root / "frontend" / "vendor").mkdir(parents=True)
            (root / "frontend" / "vendor" / "lib.js").write_text("x=1\n", encoding="utf-8")
            config = {
                "python_roots": ["services"],
                "python_globs": [],
                "frontend_roots": ["frontend"],
                "frontend_extensions": [".js"],
                "exclude_parts": ["vendor"],
                "exclude_files": [],
            }
            result = collect(root, config)
            self.assertEqual(result["files"], 1)
            self.assertEqual(result["lines"], 2)

    def test_config_has_budget(self):
        config = json.loads(Path("docs/architecture/code-budget.json").read_text(encoding="utf-8"))
        self.assertEqual(config["limit"], 150000)
        self.assertLess(config["warning"], config["limit"])


if __name__ == "__main__":
    unittest.main()
