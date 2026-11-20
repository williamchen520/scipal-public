import unittest

from code_rag.answer import build_prompt, evidence, extractive_answer, validate_citations


HITS = [
    {"unit_id": "u1", "symbol_name": "read_h5ad", "path": "src/anndata/_io/h5ad.py",
     "start_line": 241, "end_line": 343, "snippet": "def read_h5ad(...)", "source_url": "https://example/x"},
]


class CodeAnswerTest(unittest.TestCase):
    def test_evidence_and_extractive(self):
        items = evidence(HITS)
        self.assertEqual(items[0]["id"], "E1")
        self.assertIn("[E1]", extractive_answer("read h5ad", items))

    def test_prompt_contains_evidence(self):
        system, user = build_prompt("read h5ad", evidence(HITS))
        self.assertIn("only", system)
        self.assertIn("[E1]", user)

    def test_validate_citations(self):
        items = evidence(HITS)
        self.assertTrue(validate_citations("见 [E1]", items))
        self.assertFalse(validate_citations("见 [E2]", items))
        self.assertFalse(validate_citations("没有引用", items))
        self.assertTrue(validate_citations("证据不足。", items))

    def test_refusal_without_hits(self):
        self.assertEqual(extractive_answer("q", []), "证据不足。")


if __name__ == "__main__":
    unittest.main()
