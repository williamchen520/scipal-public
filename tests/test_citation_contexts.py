from __future__ import annotations

import unittest

from scripts.build_citation_contexts import expand_refs, extract_contexts


CITATIONS = {1: {"citation_id": "c1", "paper_id": "p1", "doi": "10.1/a", "title": "A"},
             2: {"citation_id": "c2", "paper_id": "p1", "doi": "10.1/b", "title": "B"}}


class CitationContextTest(unittest.TestCase):
    def test_expand_refs(self):
        self.assertEqual(expand_refs("1,3-4"), [1, 3, 4])

    def test_extract_bracket(self):
        rows = extract_contexts("Prior work [1] found X. Later [2] disagreed.", CITATIONS)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["ref_number"], 1)
        self.assertEqual(rows[0]["context"][:20], "Prior work [1] found")
        self.assertEqual(rows[0]["sentiment"], "unknown")

    def test_unknown_ref_skipped(self):
        rows = extract_contexts("Missing [9].", CITATIONS)
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
