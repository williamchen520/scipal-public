"""C2 source hygiene tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from code_rag.source_meta import detect_license, is_generated, is_vendored, scan_secrets


class SourceMetaTests(unittest.TestCase):
    def test_scan_secrets(self) -> None:
        found = scan_secrets('AWS_KEY = "AKIAABCDEFGHIJKLMNOP"\n')
        self.assertTrue(any(kind == "aws_access_key" for _, kind in found))

    def test_detect_license(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LICENSE").write_text("MIT License\nPermission is hereby granted, free of charge", encoding="utf-8")
            self.assertEqual(detect_license(root), "MIT")

    def test_generated_vendored(self) -> None:
        self.assertTrue(is_vendored("third_party/lib/x.py"))
        self.assertTrue(is_generated("src/generated/api.py"))
        self.assertFalse(is_vendored("src/app.py"))


if __name__ == "__main__":
    unittest.main()
