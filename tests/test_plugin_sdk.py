from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from flask import Blueprint, jsonify

from plugins.registry import load_enabled
from plugins.sdk import PluginError, load_manifest


class PluginSdkTest(unittest.TestCase):
    def test_manifest_and_load_unload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_dir = root / "echo"
            plugin_dir.mkdir()
            (plugin_dir / "plugin.toml").write_text(
                'id="echo"\nversion="1.0"\ncore_api="1"\nentrypoint="echo_plugin:register"\n',
                encoding="utf-8",
            )
            (root / "echo_plugin.py").write_text(
                "from flask import Blueprint, jsonify\n"
                "def register(ctx):\n"
                "    bp = Blueprint('echo', __name__)\n"
                "    @bp.get('/api/echo')\n"
                "    def echo():\n"
                "        return jsonify({'ok': True})\n"
                "    return bp\n",
                encoding="utf-8",
            )
            sys.path.insert(0, str(root))
            try:
                from flask import Flask

                enabled_app = Flask(__name__)
                self.assertEqual(load_enabled(enabled_app, root=root, enabled={"echo"}), ["echo"])
                self.assertEqual(enabled_app.test_client().get("/api/echo").status_code, 200)

                disabled_app = Flask(__name__)
                self.assertEqual(load_enabled(disabled_app, root=root, enabled=set()), [])
                self.assertEqual(disabled_app.test_client().get("/api/echo").status_code, 404)
            finally:
                sys.path.remove(str(root))

    def test_bad_core_api_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plugin.toml"
            path.write_text('id="x"\nversion="1"\ncore_api="999"\nentrypoint="x:r"\n', encoding="utf-8")
            with self.assertRaises(PluginError):
                load_manifest(path)


if __name__ == "__main__":
    unittest.main()
