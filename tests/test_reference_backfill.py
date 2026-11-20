"""Backfill and abstract availability tests."""

from __future__ import annotations

import unittest
from unittest import mock

from services.papers import reference_backfill
from services.search.abstract_search import AbstractSearch


class ReferenceBackfillTests(unittest.TestCase):
    def test_paper_id_is_stable(self) -> None:
        self.assertEqual(
            reference_backfill._paper_id("W123"),
            reference_backfill._paper_id("W123"),
        )
        self.assertNotEqual(
            reference_backfill._paper_id("W123"),
            reference_backfill._paper_id("W124"),
        )

    def test_dry_run_does_not_write(self) -> None:
        with mock.patch.object(
            reference_backfill, "top_referenced", return_value=["W1"]
        ), mock.patch.object(
            reference_backfill.metadata_sources,
            "openalex_works_by_ids",
            return_value=[
                {
                    "openalex_id": "W1",
                    "title": "T",
                    "doi": "10.1/x",
                    "cited_by_count": 5,
                }
            ],
        ):
            result = reference_backfill.backfill(limit=1, dry_run=True, dsn="ignored")
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["candidates"][0]["openalex_id"], "W1")


class AbstractAvailabilityTests(unittest.TestCase):
    def test_abstract_search_is_explicitly_unavailable(self) -> None:
        self.assertFalse(AbstractSearch().available())


if __name__ == "__main__":
    unittest.main()
