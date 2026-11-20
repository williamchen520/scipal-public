"""P2: auditable alias table tests."""

from __future__ import annotations

import unittest

from code_rag.aliases import alias_rows, expand_query, load_aliases


class AliasTests(unittest.TestCase):
    def test_quality_control_expands_to_fastqc(self) -> None:
        expanded = expand_query("quality control fastq")
        self.assertIn("fastqc", expanded)
        self.assertIn("qc", expanded)

    def test_table_rows_have_rationale_and_source(self) -> None:
        rows = alias_rows()
        self.assertTrue(rows)
        for row in rows:
            self.assertTrue(row.get("phrase"))
            self.assertTrue(row.get("aliases"))
            self.assertTrue(row.get("reason"))
            self.assertTrue(row.get("source"))

    def test_loader_is_versioned(self) -> None:
        table, payload = load_aliases()
        self.assertTrue(table)
        self.assertGreaterEqual(payload.get("version", 0), 1)


if __name__ == "__main__":
    unittest.main()
