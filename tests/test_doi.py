from __future__ import annotations

import unittest

from build_db.doi import extract_doi
from build_db.fix_missing_dois import extract_doi_from_text
from build_db.jats_parser import parse_jats
from build_db.parsers.grobid_parser import find_doi_in_text


class DoiParserTest(unittest.TestCase):
    def test_parentheses_and_punctuation(self):
        self.assertEqual(
            extract_doi("Mol Cell 2002. 10.1016/S1097-2765(02)00470-7."),
            "10.1016/s1097-2765(02)00470-7",
        )

    def test_url_prefix(self):
        self.assertEqual(
            extract_doi("https://doi.org/10.1038/S41586-023-06547-X"),
            "10.1038/s41586-023-06547-x",
        )

    def test_truncated_rejected(self):
        self.assertEqual(extract_doi("10.1016/S1097-2765(02"), "")

    def test_all_entrypoints_agree(self):
        text = "doi:10.1016/S1097-2765(02)00470-7"
        expected = "10.1016/s1097-2765(02)00470-7"
        self.assertEqual(extract_doi(text), expected)
        self.assertEqual(extract_doi_from_text(text), expected)
        self.assertEqual(find_doi_in_text(text), expected)

    def test_jats_reference(self):
        xml = '<article><body><ref-list><ref id="R1"><mixed-citation>10.1016/S1097-2765(02)00470-7</mixed-citation></ref></ref-list></body></article>'
        self.assertEqual(parse_jats(xml)["references"][0]["doi"], "10.1016/s1097-2765(02)00470-7")


if __name__ == "__main__":
    unittest.main()
