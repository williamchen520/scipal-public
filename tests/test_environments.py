import tempfile
import unittest
from pathlib import Path

from code_rag.environments import detect


class EnvironmentTest(unittest.TestCase):
    def test_pyproject(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text(
                '[project]\nname="demo"\nversion="1.2.3"\n', encoding="utf-8"
            )
            env = detect(root, language="python", ref="v1")
            self.assertEqual(env["manager"], "pyproject")
            self.assertEqual(env["base_version"], "1.2.3")
            self.assertEqual(env["project_name"], "demo")
            self.assertTrue(env["environment_id"].startswith("env_"))

    def test_r_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "DESCRIPTION").write_text("Package: demo\nVersion: 2.0.0\n", encoding="utf-8")
            env = detect(root, language="r", ref="main")
            self.assertEqual(env["manager"], "renv")
            self.assertEqual(env["base_version"], "2.0.0")

    def test_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = detect(Path(tmp), language="python", ref="main")
            self.assertEqual(env["manager"], "unknown")
            self.assertEqual(env["base_version"], "main")


if __name__ == "__main__":
    unittest.main()
