import unittest

from eval.eval_spec import canonical_hash, validate


BASE = {
    "id": "t",
    "metric": "ndcg@10",
    "dataset": "d",
    "corpus": "c",
    "split": "s",
    "sample_size": 100,
    "baseline": "bm25",
    "external_anchor": "CoIR",
    "heldout": "yes",
    "owner": "o",
    "reviewer": "r",
    "decision_rule": "candidate >= baseline",
}


class EvalSpecTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate(BASE), [])

    def test_missing_baseline(self):
        spec = dict(BASE)
        spec["baseline"] = ""
        self.assertIn("missing:baseline", validate(spec))

    def test_threshold_requires_basis(self):
        spec = dict(BASE, threshold=0.85, threshold_basis="")
        self.assertIn("threshold_without_basis", validate(spec))

    def test_hash_is_stable(self):
        self.assertEqual(canonical_hash(BASE), canonical_hash(dict(reversed(list(BASE.items())))))


if __name__ == "__main__":
    unittest.main()
