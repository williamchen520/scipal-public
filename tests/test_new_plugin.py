from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plugins.sdk import load_manifest
from scripts.new_plugin import scaffold


class NewPluginTest(unittest.TestCase):
    def test_scaffold_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = scaffold("demo_plugin", root / "plugins")
            manifest = load_manifest(target / "plugin.toml")
            self.assertEqual(manifest.plugin_id, "demo_plugin")
            self.assertFalse(manifest.enabled)
            self.assertIn("def register", (target / "plugin.py").read_text(encoding="utf-8"))

    def test_invalid_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                scaffold("Bad-ID", Path(tmp))
