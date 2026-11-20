from __future__ import annotations

import logging
import os
import unittest
from unittest import mock

from flask import Flask

from routes.evidence import build_evidence_blueprint


class FakeRetriever:
    def to_evidence_json(self, query, *, paper_id=None, top_paragraphs=10):
        return {
            "query": query,
            "evidence": [{
                "paper_id": "paper_P1",
                "para_id": "para_P1",
                "section_path": [],
                "text": "evidence",
                "highlight": [{"sentence_id": "s1", "text": "evidence"}],
                "matched_sentences": [{"sentence_id": "s1", "text": "evidence"}],
                "paragraph_details": [{"para_id": "para_P1", "sentence_ids": ["s1"], "text": "evidence"}],
            }],
            "sufficient": True,
            "sufficiency": {"sufficient": True, "reason": "test"},
            "summaries": [],
        }


class EvidenceAuditTest(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(build_evidence_blueprint(
            db_path=":memory:", get_retriever=lambda: FakeRetriever(), log=logging.getLogger("test")
        ))
        self.client = app.test_client()

    def test_audit_opt_in(self):
        body = self.client.post("/api/evidence/search", json={"query": "q", "audit": True}).get_json()
        self.assertIn("audit", body)
        self.assertEqual(body["audit"]["coverage"]["status"], "covered")

    def test_audit_default_off(self):
        body = self.client.post("/api/evidence/search", json={"query": "q"}).get_json()
        self.assertNotIn("audit", body)

    def test_audit_get_flag(self):
        body = self.client.get("/api/evidence/search?query=q&audit=1").get_json()
        self.assertIn("audit", body)


if __name__ == "__main__":
    unittest.main()


class BadRetriever:
    def to_evidence_json(self, query, *, paper_id=None, top_paragraphs=10):
        return {
            "evidence": [{"paper_id": "paper_P1", "para_id": "", "highlight": [{"sentence_id": "s1"}]}],
            "sufficiency": {"reason": "bad"},
        }


class EvidenceAuditModeTest(unittest.TestCase):
    def test_default_on_without_query_flag(self):
        app = Flask(__name__)
        app.register_blueprint(build_evidence_blueprint(
            db_path=":memory:", get_retriever=lambda: FakeRetriever(), log=logging.getLogger("test")
        ))
        with mock.patch.dict(os.environ, {"SCIPAL_EVIDENCE_AUDIT": "on"}):
            body = app.test_client().post("/api/evidence/search", json={"query": "q"}).get_json()
        self.assertIn("audit", body)

    def test_explicit_off_overrides_default(self):
        app = Flask(__name__)
        app.register_blueprint(build_evidence_blueprint(
            db_path=":memory:", get_retriever=lambda: FakeRetriever(), log=logging.getLogger("test")
        ))
        with mock.patch.dict(os.environ, {"SCIPAL_EVIDENCE_AUDIT": "on"}):
            body = app.test_client().post("/api/evidence/search", json={"query": "q", "audit": False}).get_json()
        self.assertNotIn("audit", body)

    def test_required_rejects_incomplete_provenance(self):
        app = Flask(__name__)
        app.register_blueprint(build_evidence_blueprint(
            db_path=":memory:", get_retriever=lambda: BadRetriever(), log=logging.getLogger("test")
        ))
        with mock.patch.dict(os.environ, {"SCIPAL_EVIDENCE_AUDIT": "required"}):
            response = app.test_client().post("/api/evidence/search", json={"query": "q"})
        self.assertEqual(response.status_code, 503)
