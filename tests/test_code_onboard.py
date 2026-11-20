import unittest

from scripts.code_onboard import commands, display, validate


BASE = {
    "library_id": "lib_test",
    "path": "D:/sciPal",
    "repo_url": "https://example.com/repo",
    "language": "python",
}


class CodeOnboardTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate(BASE), [])

    def test_missing_library(self):
        self.assertIn("missing:library_id", validate(dict(BASE, library_id="")))

    def test_invalid_language(self):
        self.assertIn("invalid:language:java", validate(dict(BASE, language="java")))

    def test_display_redacts_password(self):
        text = display(["psql", "postgresql://user:secret@host/db"])
        self.assertNotIn("secret", text)
        self.assertIn("***:***@", text)

    def test_commands_order(self):
        commands_list = commands(
            BASE, full=False, dsn="postgresql://u:p@h/db", bm25_dsn="postgresql://u:p@h/g0"
        )
        self.assertEqual(len(commands_list), 3)
        self.assertIn("code_rag.ingest", commands_list[0])
        self.assertIn("code_rag.resolve", commands_list[1])
        self.assertIn("code_rag.bm25", commands_list[2])


if __name__ == "__main__":
    unittest.main()
