from __future__ import annotations

import unittest

from scripts.reparse_jats_citations import _aligned


class ReparseJatsTest(unittest.TestCase):
    def test_aligned_titles(self):
        self.assertTrue(_aligned("Array programming with NumPy", "Array programming with NumPy"))
        self.assertFalse(_aligned("Array programming with NumPy", "A different paper"))


if __name__ == "__main__":
    unittest.main()
