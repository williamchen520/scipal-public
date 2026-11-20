from __future__ import annotations

import unittest

from scripts.repair_citation_dois import extract_doi


class RepairCitationDoiTest(unittest.TestCase):
    def test_parentheses_doi(self):
        self.assertEqual(
            extract_doi("Mol. Cell 2002. 10.1016/S1097-2765(02)00470-7"),
            "10.1016/s1097-2765(02)00470-7",
        )

    def test_truncated_doi_not_returned(self):
        self.assertEqual(extract_doi("10.1016/S1097-2765(02"), "")


if __name__ == "__main__":
    unittest.main()
