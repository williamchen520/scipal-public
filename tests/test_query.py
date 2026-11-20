import unittest

from code_rag.query import parse_query


class QueryParserTest(unittest.TestCase):
    def test_default(self):
        parsed = parse_query("normalize counts")
        self.assertEqual(parsed.query, "normalize counts")
        self.assertEqual(parsed.mode, "")

    def test_regex(self):
        parsed = parse_query("re:def\\s+normalize")
        self.assertEqual(parsed.mode, "regex")
        self.assertEqual(parsed.query, "def\\s+normalize")

    def test_path(self):
        parsed = parse_query("path:preprocessing normalize")
        self.assertEqual(parsed.path_filter, "preprocessing")
        self.assertEqual(parsed.query, "normalize")

    def test_lang(self):
        parsed = parse_query("lang:python normalize")
        self.assertEqual(parsed.language, "python")
        self.assertEqual(parsed.query, "normalize")

    def test_symbol_maps_to_regex(self):
        parsed = parse_query("sym:read_h5ad")
        self.assertEqual(parsed.mode, "regex")
        self.assertEqual(parsed.query, "read_h5ad")


if __name__ == "__main__":
    unittest.main()
