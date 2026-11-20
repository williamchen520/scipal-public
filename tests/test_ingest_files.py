import tempfile
import unittest
from pathlib import Path

from code_rag.ingest import files_for


class IngestFilesTest(unittest.TestCase):
    def test_skips_virtualenv_and_node_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text("def f():\n    return 1\n", encoding="utf-8")
            (root / "venv_sciPal_py312").mkdir()
            (root / "venv_sciPal_py312" / "site.py").write_text("x=1\n", encoding="utf-8")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "x.py").write_text("x=1\n", encoding="utf-8")
            names = [path.name for path in files_for(root, "python", 0)]
            self.assertEqual(names, ["app.py"])


if __name__ == "__main__":
    unittest.main()
