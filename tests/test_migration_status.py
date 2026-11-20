from __future__ import annotations

import unittest

from scripts.migration_status import check


class MigrationStatusTest(unittest.TestCase):
    def test_lock_matches_files(self) -> None:
        self.assertEqual(check(), [])


if __name__ == "__main__":
    unittest.main()
