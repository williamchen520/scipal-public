import unittest

from scripts.code_feedback_to_cases import convert, language_for


class FeedbackCasesTest(unittest.TestCase):
    def test_convert(self):
        items = [
            {
                "event_id": "e" * 12,
                "library_id": "lib_x",
                "query": "read h5ad",
                "expected_path": "src/x.py",
            }
        ]
        cases = convert(items)
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["category"], "feedback")
        self.assertEqual(cases[0]["expected_symbol"], "")
        self.assertEqual(cases[0]["language"], "python")

    def test_skip_missing_path(self):
        self.assertEqual(
            convert([{"event_id": "e", "library_id": "x", "query": "q", "expected_path": ""}]),
            [],
        )

    def test_dedupe(self):
        item = {
            "event_id": "e",
            "library_id": "x",
            "query": "q",
            "expected_path": "x.py",
        }
        self.assertEqual(len(convert([item, dict(item)])), 1)

    def test_language(self):
        self.assertEqual(language_for("x.R"), "r")
        self.assertEqual(language_for("x.nf"), "nextflow")


if __name__ == "__main__":
    unittest.main()
