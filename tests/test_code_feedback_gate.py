import unittest

from scripts.code_feedback_gate import file_rank, summarize


class FeedbackGateTest(unittest.TestCase):
    def test_file_rank(self):
        hits = [{"path": "a"}, {"path": "b"}]
        self.assertEqual(file_rank(hits, "b"), 2)
        self.assertIsNone(file_rank(hits, "c"))

    def test_summarize(self):
        self.assertEqual(summarize([]), {"cases": 0, "file@1": None, "file@3": None})
        result = summarize([1, 3, None])
        self.assertEqual(result["cases"], 3)
        self.assertEqual(result["file@1"], 0.3333)
        self.assertEqual(result["file@3"], 0.6667)


if __name__ == "__main__":
    unittest.main()
