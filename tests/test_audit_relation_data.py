from __future__ import annotations

import unittest

from scripts.audit_relation_data import normalize_doi


class AuditRelationDataTest(unittest.TestCase):
    def test_normalize_doi(self):
        self.assertEqual(normalize_doi("https://doi.org/10.1/ABC"), "10.1/abc")
        self.assertEqual(normalize_doi("doi: 10.1/ABC"), "10.1/abc")


if __name__ == "__main__":
    unittest.main()
