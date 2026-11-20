"""QA sentence adapter contract tests."""

from __future__ import annotations

import unittest

from services.qa.sentence_retriever import SentenceQARetriever


class _Base:
    def search(self, query, top_k=10):
        return [
            {
                "sentence_id": "s1",
                "para_id": "p1",
                "paper_id": "paper1",
                "text": "Full paragraph text",
                "anchor_text": "Answer sentence",
                "section_path": ["Results"],
                "anchor_score": 0.9,
            }
        ]


class SentenceQAAdapterTests(unittest.TestCase):
    def test_retrieve_and_envelope(self) -> None:
        retriever = SentenceQARetriever(base=_Base())
        env = retriever.retrieve("q", top_paragraphs=5)
        self.assertEqual(env["paragraphs"][0]["para_id"], "p1")
        text = retriever.envelope_from_result("q", env)
        self.assertIn("[P1]", text)
        self.assertIn("Full paragraph text", text)

    def test_paper_scope(self) -> None:
        retriever = SentenceQARetriever(base=_Base())
        env = retriever.retrieve("q", paper_id="other")
        self.assertEqual(env["paragraphs"], [])


if __name__ == "__main__":
    unittest.main()
