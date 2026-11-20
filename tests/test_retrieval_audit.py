from __future__ import annotations

import unittest

from services.audit.retrieval_audit import build_audit_record, validate_audit_record


class RetrievalAuditTest(unittest.TestCase):
    def test_covered_record(self):
        bundle = {
            "sufficiency": {"sufficient": True, "reason": "sentence_backend"},
            "evidence": [{
                "paper_id": "paper_P1",
                "para_id": "para_P1",
                "highlight": [{"sentence_id": "s1", "text": "evidence", "page": 1}],
            }],
        }
        record = build_audit_record(query="q", bundle=bundle, config_id="cfg")
        self.assertEqual(record["coverage"]["status"], "covered")
        self.assertTrue(record["coverage"]["provenance_complete"])
        self.assertEqual(validate_audit_record(record), [])

    def test_empty_record(self):
        record = build_audit_record(query="q", bundle={"evidence": []})
        self.assertEqual(record["coverage"]["status"], "empty")
        self.assertFalse(record["coverage"]["provenance_complete"])

    def test_incomplete_provenance(self):
        bundle = {"evidence": [{"paper_id": "p", "highlight": [{"text": "x"}]}]}
        record = build_audit_record(query="q", bundle=bundle)
        self.assertEqual(record["coverage"]["status"], "partial")
        self.assertTrue(validate_audit_record(record))

    def test_schema_version(self):
        record = build_audit_record(query="q", bundle={"evidence": []})
        record["schema_version"] = "999"
        self.assertIn("schema_version mismatch", validate_audit_record(record))


if __name__ == "__main__":
    unittest.main()


class FacetCoverageTest(unittest.TestCase):
    def test_facet_partial(self):
        bundle = {"evidence": [{
            "paper_id": "p", "para_id": "para",
            "highlight": [{"sentence_id": "s", "text": "ICI response study"}],
        }]}
        record = build_audit_record(query="ICI rechallenge", bundle=bundle)
        self.assertEqual(record["coverage"]["facet_status"], "partial")
        self.assertEqual(record["coverage"]["missing_facet_count"], 1)
        missing = [row["facet"] for row in record["coverage"]["facet_details"] if not row["covered"]]
        self.assertEqual(missing, ["rechallenge"])
        self.assertEqual(record["coverage"]["claim_coverage"], "not_computed")

    def test_facet_covered(self):
        bundle = {"evidence": [{
            "paper_id": "p", "para_id": "para",
            "highlight": [{"sentence_id": "s", "text": "ICI rechallenge improves response"}],
        }]}
        record = build_audit_record(query="ICI rechallenge", bundle=bundle)
        self.assertEqual(record["coverage"]["facet_status"], "covered")
