import sys
import unittest

sys.path.insert(0, "src")
import mathmod


class MathTest(unittest.TestCase):
    def test_add(self):
        self.assertEqual(mathmod.add(2, 3), 5)

    def test_sub(self):
        self.assertEqual(mathmod.sub(5, 3), 2)
