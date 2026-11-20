from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from services.search import retrieval_trace


class RetrievalTraceTest(unittest.TestCase):
    def test_config_id_stable(self):
        config = {"backend": "sentence_hybrid", "lexical_weight": 0.7}
        self.assertEqual(retrieval_trace.config_id(config), retrieval_trace.config_id(dict(config)))
        self.assertNotEqual(retrieval_trace.config_id(config), retrieval_trace.config_id({**config, "lexical_weight": 0.6}))

    def test_record_writes_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("SCIPAL_RETRIEVAL_TRACE_PATH")
            os.environ["SCIPAL_RETRIEVAL_TRACE_PATH"] = str(Path(tmp) / "trace.jsonl")
            try:
                record = retrieval_trace.record(
                    query="q",
                    config={"lexical_weight": 0.7},
                    pool=[{"sentence_id": "s1"}],
                    final=[{"sentence_id": "s1"}],
                    latency_ms=1.2,
                )
                rows = [json.loads(line) for line in (Path(tmp) / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
            finally:
                if old is None:
                    os.environ.pop("SCIPAL_RETRIEVAL_TRACE_PATH", None)
                else:
                    os.environ["SCIPAL_RETRIEVAL_TRACE_PATH"] = old
            self.assertEqual(rows[0]["trace_id"], record["trace_id"])
            self.assertEqual(rows[0]["config_id"], retrieval_trace.config_id({"lexical_weight": 0.7}))


if __name__ == "__main__":
    unittest.main()
