from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.ledger import build_ledger_blueprint


class FakeLLM:
    def chat(self, system_prompt, user_prompt, temperature=None):
        return "Rewritten [P1]."


class FakeQA:
    llm = FakeLLM()
from services.audit.ledger_store import save


class LedgerApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("SCIPAL_LEDGER_PATH")
        self.old_actions = os.environ.get("SCIPAL_LEDGER_ACTIONS_PATH")
        os.environ["SCIPAL_LEDGER_PATH"] = str(Path(self.tmp.name) / "ledgers.jsonl")
        os.environ["SCIPAL_LEDGER_ACTIONS_PATH"] = str(Path(self.tmp.name) / "actions.jsonl")
        self.old_chain = os.environ.get("SCIPAL_EVENT_CHAIN_PATH")
        os.environ["SCIPAL_EVENT_CHAIN_PATH"] = str(Path(self.tmp.name) / "chain.jsonl")
        save({"answer_id": "a1", "query": "q", "created_at": "now", "summary": {"evidence": 1}})
        save({
            "answer_id": "a2", "query": "q", "claims": [{"claim_id": "cl_1", "cited_sentence_ids": ["s1"], "known_sentence_ids": ["s1"], "support_status": "cited"}],
            "evidence": [{"sentence_id": "s1", "paper_id": "p1", "text": "evidence", "cited": True, "review_priority": "low"}], "summary": {},
        })
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(build_ledger_blueprint(get_qa_service=lambda: FakeQA()))
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = "u"

    def tearDown(self):
        if self.old is None:
            os.environ.pop("SCIPAL_LEDGER_PATH", None)
        else:
            os.environ["SCIPAL_LEDGER_PATH"] = self.old
        if self.old_actions is None:
            os.environ.pop("SCIPAL_LEDGER_ACTIONS_PATH", None)
        else:
            os.environ["SCIPAL_LEDGER_ACTIONS_PATH"] = self.old_actions
        if self.old_chain is None:
            os.environ.pop("SCIPAL_EVENT_CHAIN_PATH", None)
        else:
            os.environ["SCIPAL_EVENT_CHAIN_PATH"] = self.old_chain
        self.tmp.cleanup()

    def test_list_and_get(self):
        body = self.client.get("/api/audit/ledgers").get_json()
        self.assertIn("a1", [row["answer_id"] for row in body["ledgers"]])
        self.assertEqual(self.client.get("/api/audit/ledgers/a1").status_code, 200)
        self.assertEqual(self.client.get("/api/audit/ledgers/missing").status_code, 404)

    def test_record_action(self):
        response = self.client.post("/api/audit/ledgers/a1/actions", json={"action": "accept", "target_id": "cl_1"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.client.get("/api/audit/ledgers/a1/actions").get_json()["actions"][0]["action"], "accept")

    def test_chain_verification(self):
        self.client.post("/api/audit/ledgers/a1/actions", json={"action": "accept", "target_id": "cl_1"})
        body = self.client.get("/api/audit/ledgers/a1/chain").get_json()
        self.assertTrue(body["verification"]["ok"])
        self.assertEqual(body["verification"]["events"], 1)

    def test_close_computes_verification(self):
        rev = self.client.post("/api/audit/ledgers/a2/revisions", json={"action": "rewrite_claim", "target_id": "cl_1", "new_text": "new [P1]", "evidence_ids": ["s1"]}).get_json()
        error_id = rev["error"]["error_id"]
        self.client.post(f"/api/audit/errors/{error_id}/transition", json={"status": "verified"})
        response = self.client.post(f"/api/audit/errors/{error_id}/transition", json={"status": "closed", "revision_answer_id": rev["ledger"]["answer_id"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "closed")

    def test_rewrite_returns_draft(self):
        response = self.client.post("/api/audit/ledgers/a2/rewrite", json={"claim_id": "cl_1", "evidence_ids": ["s1"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["draft"], "Rewritten [P1].")

    def test_revision_returns_repaired_error(self):
        response = self.client.post("/api/audit/ledgers/a2/revisions", json={"action": "remove_claim", "target_id": "cl_1"})
        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["ledger"]["parent_answer_id"], "a2")
        self.assertEqual(body["error"]["status"], "repaired")
        self.assertEqual(body["error"]["revision_answer_id"], body["ledger"]["answer_id"])

    def test_requires_login(self):
        client = Flask(__name__).test_client()
        client.application.register_blueprint(build_ledger_blueprint())
        self.assertEqual(client.get("/api/audit/ledgers").status_code, 401)
