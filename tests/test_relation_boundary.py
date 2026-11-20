from __future__ import annotations

import unittest
from pathlib import Path

CORE_DIRS = ["routes", "services", "code_rag", "build_db", "contracts", "mcp_server", "plugins"]
FORBIDDEN = ("relation_retrieval", "relation_prior", "co_citation", "bibliographic_coupling")


class RelationBoundaryTest(unittest.TestCase):
    def test_relation_algorithm_stays_out_of_core(self):
        offenders = []
        for directory in CORE_DIRS:
            root = Path(directory)
            if not root.exists():
                continue
            for path in root.rglob("*.py"):
                text = path.read_text(encoding="utf-8", errors="ignore")
                for token in FORBIDDEN:
                    if token in text:
                        offenders.append(f"{path}:{token}")
        self.assertEqual(offenders, [], "relation algorithm must stay in scripts/ until promoted")


if __name__ == "__main__":
    unittest.main()
