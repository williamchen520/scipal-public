import unittest

from code_rag.source_link import source_url


class SourceLinkTest(unittest.TestCase):
    def test_github_blob(self):
        url = source_url("https://github.com/scverse/scanpy", "abc123", "src/scanpy/x.py", 10, 20)
        self.assertEqual(
            url,
            "https://github.com/scverse/scanpy/blob/abc123/src/scanpy/x.py#L10-L20",
        )

    def test_strip_git_suffix(self):
        self.assertEqual(
            source_url("https://github.com/a/b.git", "c", "x.py", 1, 1),
            "https://github.com/a/b/blob/c/x.py#L1",
        )

    def test_missing_fields(self):
        self.assertEqual(source_url("", "c", "x.py", 1, 1), "")
        self.assertEqual(source_url("https://github.com/a/b", "", "x.py", 1, 1), "")


if __name__ == "__main__":
    unittest.main()
