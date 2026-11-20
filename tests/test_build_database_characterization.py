"""Characterization tests for legacy build_database pure helpers.

Importing build_database loads docling; these tests do not run the legacy
pipeline or touch a database.
"""

from __future__ import annotations

import unittest

from build_db.build_database import (
    extract_doi,
    extract_doi_from_filename,
    extract_fig_refs,
    generate_id,
    generate_paper_id,
    is_grobid_title_suspicious,
    is_noise_paragraph,
    is_noise_section,
    is_reference_like_section,
    is_reference_section,
    journal_from_doi,
)


class BuildDatabaseCharacterizationTests(unittest.TestCase):
    def test_section_filters(self):
        self.assertTrue(is_noise_section(""))
        self.assertTrue(is_noise_section("Figure 1"))
        self.assertFalse(is_noise_section("Results"))
        self.assertTrue(is_reference_section("References"))
        self.assertTrue(is_reference_section("Bibliography"))
        self.assertFalse(is_reference_section("Results"))
        self.assertTrue(is_reference_like_section("1. Smith J. A title"))
        self.assertFalse(is_reference_like_section("Introduction"))

    def test_paragraph_filter(self):
        self.assertTrue(is_noise_paragraph("Contents lists available at ScienceDirect"))
        self.assertTrue(is_noise_paragraph(""))
        self.assertFalse(is_noise_paragraph("We measured STAT1 phosphorylation."))

    def test_grobid_title(self):
        self.assertEqual(is_grobid_title_suspicious(""), (True, "empty"))
        self.assertTrue(is_grobid_title_suspicious("TRANSLATIONAL RESEARCH IN HEART FAILURE")[0])
        self.assertTrue(is_grobid_title_suspicious("Estonian Biobank Research Team")[0])
        self.assertFalse(is_grobid_title_suspicious("STAT1 signaling in immunity")[0])

    def test_identifiers(self):
        self.assertTrue(generate_paper_id("test.pdf").startswith("paper_test_"))
        self.assertEqual(generate_id("para", "p1", 3), "para_p1_0003")

    def test_doi_extraction(self):
        self.assertEqual(extract_doi("doi: 10.1038/s41586-023-06547-x."), "10.1038/s41586-023-06547-x")
        self.assertEqual(
            extract_doi("https://doi.org/10.1002/ctm2.206"),
            "10.1002/ctm2.206",
        )
        self.assertIsNone(extract_doi("no doi here"))

    def test_doi_from_filename(self):
        self.assertEqual(
            extract_doi_from_filename("s41586-023-06547-x.pdf"),
            "10.1038/s41586-023-06547-x",
        )
        self.assertEqual(
            extract_doi_from_filename("s10555-020-09883-w.pdf"),
            "10.1007/s10555-020-09883-w",
        )
        self.assertEqual(extract_doi_from_filename("CTM2-10-e206.pdf"), "10.1002/ctm2.206")
        self.assertIsNone(extract_doi_from_filename("random.pdf"))

    def test_journal_and_figures(self):
        self.assertEqual(journal_from_doi("10.1038/s41586-023-06547-x"), "Nature")
        self.assertIsNone(journal_from_doi("10.9999/unknown"))
        self.assertEqual(extract_fig_refs("Fig. 1, Figure 2 and Table 3"), ["1", "2", "3"])


if __name__ == "__main__":
    unittest.main()
