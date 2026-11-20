import unittest

from code_rag.feedback import record_event, record_feedback


class FeedbackTest(unittest.TestCase):
    def test_invalid_verdict(self):
        ok, error = record_feedback(dsn="", library_id="x", event_id="e", verdict="bad")
        self.assertFalse(ok)
        self.assertEqual(error, "invalid verdict")

    def test_no_dsn_event(self):
        self.assertEqual(
            record_event(
                dsn="", library_id="x", query="q", mode="", backend="bm25",
                top_k=10, latency_ms=1.0, hits=[],
            ),
            "",
        )


if __name__ == "__main__":
    unittest.main()
