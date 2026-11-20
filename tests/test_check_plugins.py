from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_plugins import check_plugin


class CheckPluginsTest(unittest.TestCase):
    def test_rejects_core_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "bad"
            root.mkdir()
            (root / "plugin.toml").write_text(
                'id="bad"\nversion="1"\ncore_api="1"\nentrypoint="bad.plugin:register"\n',
                encoding="utf-8",
            )
            (root / "plugin.py").write_text("from services.db.pg_pool import pg_connection\n", encoding="utf-8")
            errors = check_plugin(root)
            self.assertTrue(any("core internal" in error for error in errors))

    def test_data_plugin_passes(self):
        root = Path("plugins/data_sandbox")
        self.assertEqual(check_plugin(root), [])


if __name__ == "__main__":
    unittest.main()
