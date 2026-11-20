from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_code_rag_tasks import validate


class CodeRagTasksTest(unittest.TestCase):
    def test_valid_fixture(self):
        self.assertEqual(validate(Path("eval/code_rag_tasks.jsonl")), [])

    def test_missing_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "repo").mkdir()
            (root / "repo" / "test_x.py").write_text("", encoding="utf-8")
            tasks = root / "tasks.jsonl"
            tasks.write_text('{"task_id":"x","repo":"repo","target_paths":["missing.py"],"test_module":"test_x"}', encoding="utf-8")
            self.assertTrue(validate(tasks))


if __name__ == "__main__":
    unittest.main()
