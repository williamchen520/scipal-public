from __future__ import annotations

import unittest

from services.qa.evidence_rewrite import build_prompt, rewrite


class FakeLLM:
    def __init__(self, text):
        self.text = text

    def chat(self, system_prompt, user_prompt, temperature=None):
        self.prompt = user_prompt
        return self.text


class EvidenceRewriteTest(unittest.TestCase):
    def _evidence(self):
        return [
            {"sentence_id": "s1", "text": "ICI improves response."},
            {"sentence_id": "s2", "text": "Rechallenge was studied."},
        ]

    def test_rewrite_uses_selected(self):
        llm = FakeLLM("ICI improves response [P1]. Rechallenge was studied [P2].")
        result = rewrite(question="q", paragraph="old", evidence=self._evidence(), llm=llm)
        self.assertEqual(result["status"], "draft")
        self.assertEqual(result["used_sentence_ids"], ["s1", "s2"])
        self.assertIn("[P1]", llm.prompt)

    def test_out_of_scope_rejected(self):
        llm = FakeLLM("Outside fact [P3].")
        result = rewrite(question="q", paragraph="old", evidence=self._evidence(), llm=llm)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "out_of_scope_evidence")
        self.assertEqual(result["unknown_labels"], ["[P3]"])

    def test_no_evidence(self):
        result = rewrite(question="q", paragraph="old", evidence=[], llm=FakeLLM("x"))
        self.assertEqual(result["reason"], "no_evidence")

    def test_prompt_contains_question_and_paragraph(self):
        prompt = build_prompt(question="q", paragraph="old", evidence=self._evidence())
        self.assertIn("q", prompt)
        self.assertIn("old", prompt)
        self.assertIn("[P2]", prompt)


if __name__ == "__main__":
    unittest.main()
