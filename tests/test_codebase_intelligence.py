import tempfile
import unittest
from pathlib import Path

from scripts.check_import_boundaries import check
from scripts.export_routes import app_keys, json_keys


class CodebaseIntelligenceTest(unittest.TestCase):
    def test_boundary_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "code_rag").mkdir()
            (root / "code_rag" / "bad.py").write_text("from routes import x\n", encoding="utf-8")
            violations = check(root)
            self.assertEqual(len(violations), 1)
            self.assertEqual(violations[0]["module"], "code_rag.bad")
            self.assertEqual(violations[0]["imports"], "routes")

    def test_build_db_may_import_services(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "build_db").mkdir()
            (root / "build_db" / "ok.py").write_text("from services.db import pg\n", encoding="utf-8")
            self.assertEqual(check(root), [])

    def test_route_keys(self):
        arch = {"api": {"endpoints": [{"rule": "/x", "methods": ["GET"], "status": "implemented"}]}}
        self.assertEqual(json_keys(arch), {("/x", "GET")})
        self.assertEqual(app_keys([{"rule": "/x", "method": "GET"}]), {("/x", "GET")})


if __name__ == "__main__":
    unittest.main()
