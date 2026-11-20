import json
import tempfile
import unittest
from pathlib import Path

from scripts.impact_analysis import affected, build_graph, contract_surfaces, domain_for_path, route_candidates


class ImpactAnalysisTest(unittest.TestCase):
    def test_reverse_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "code_rag").mkdir()
            (root / "services").mkdir()
            (root / "routes").mkdir()
            (root / "tests").mkdir()
            (root / "code_rag" / "b.py").write_text("x = 1\n", encoding="utf-8")
            (root / "services" / "a.py").write_text("from code_rag import b\n", encoding="utf-8")
            (root / "routes" / "r.py").write_text("from services import a\n", encoding="utf-8")
            (root / "tests" / "test_r.py").write_text("from routes import r\n", encoding="utf-8")
            graph, _ = build_graph(root)
            impacted = affected({"code_rag.b"}, graph)
            self.assertIn("services.a", impacted)
            self.assertIn("routes.r", impacted)
            self.assertIn("tests.test_r", impacted)

    def test_domain_and_contract(self):
        domains = [
            {"id": "platform", "paths": ["services/tenancy"]},
            {"id": "literature", "paths": ["services/papers"]},
        ]
        self.assertEqual(domain_for_path("services/tenancy/pg_service.py", domains), "platform")
        self.assertEqual(domain_for_path("services/papers/x.py", domains), "literature")
        self.assertEqual(domain_for_path("docs/x.md", domains), "")
        self.assertEqual(contract_surfaces(["ARCHITECTURE.json"]), ["api"])
        self.assertEqual(contract_surfaces(["docs/architecture/domains.json"]), ["domain"])
        self.assertEqual(contract_surfaces(["deploy/sql/001.sql"]), ["schema"])

    def test_route_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "routes.json"
            manifest.write_text(
                json.dumps({"routes": [{"method": "GET", "rule": "/x", "blueprint": "r"}]}),
                encoding="utf-8",
            )
            self.assertEqual(route_candidates({"routes.r"}, manifest)[0]["rule"], "/x")


if __name__ == "__main__":
    unittest.main()
