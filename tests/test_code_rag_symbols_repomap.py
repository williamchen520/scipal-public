"""P0: symbol normalization and repo map tests."""

from __future__ import annotations

import unittest

from code_rag.repomap import rollup_graph
from code_rag.symbols import normalize_symbol, symbol_terms


class SymbolTests(unittest.TestCase):
    def test_normalize_forms(self) -> None:
        self.assertEqual(normalize_symbol("read_10x_mtx"), "read 10x mtx")
        self.assertEqual(normalize_symbol("normalizeTotal"), "normalize total")
        self.assertEqual(normalize_symbol("FASTP"), "fastp")
        self.assertIn("read", symbol_terms("read_10x_mtx"))


class RepoMapTests(unittest.TestCase):
    def test_graph_rollup_and_budget(self) -> None:
        units = [
            ("u1", "a.py", "alpha", "function"),
            ("u2", "b.py", "beta", "function"),
            ("u3", "c.py", "gamma", "function"),
        ]
        edges = [("u1", "u2", "calls"), ("u2", "u3", "calls")]
        rank, symbols = rollup_graph(units, edges)
        self.assertEqual(set(rank), {"a.py", "b.py", "c.py"})
        self.assertIn("alpha", symbols["a.py"])
        self.assertGreater(rank["b.py"], rank["a.py"])

    def test_personalized_seed(self) -> None:
        units = [
            ("u1", "a.py", "alpha", "function"),
            ("u2", "b.py", "beta", "function"),
        ]
        rank, _ = rollup_graph(units, [("u1", "u2", "calls")], {"a.py": 1.0})
        self.assertGreater(rank["a.py"], rank["b.py"])


if __name__ == "__main__":
    unittest.main()
