from __future__ import annotations

import unittest

from scripts.check_domains import check


class DomainOwnershipTest(unittest.TestCase):
    def test_domains_are_well_formed(self) -> None:
        errors = check()
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
