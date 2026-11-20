from __future__ import annotations

import unittest

from scripts.sample_citation_contexts import sample


class SampleCitationContextsTest(unittest.TestCase):
    def test_spreads_sample(self):
        rows = [{"citation_id": str(index)} for index in range(100)]
        picked = sample(rows, 10)
        self.assertEqual(len(picked), 10)
        self.assertEqual(picked[0]["citation_id"], "0")
        self.assertGreaterEqual(int(picked[-1]["citation_id"]), 90)

    def test_small_input_kept(self):
        rows = [{"citation_id": "1"}]
        self.assertEqual(sample(rows, 10), rows)


if __name__ == "__main__":
    unittest.main()
