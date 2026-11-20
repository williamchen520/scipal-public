#!/usr/bin/env python3
"""Validate plugin manifests and the no-core-internals boundary."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from plugins.sdk import PluginError, load_manifest

PLUGIN_DIR = ROOT / "plugins"
FORBIDDEN = ("services", "routes", "build_db", "code_rag", "mcp_server")


def _module_for(manifest) -> str:
    return manifest.entrypoint.partition(":")[0]


def check_plugin(directory: Path) -> list[str]:
    errors = []
    manifest_path = directory / "plugin.toml"
    if not manifest_path.exists():
        return [f"{directory.name}: missing plugin.toml"]
    try:
        manifest = load_manifest(manifest_path)
    except PluginError as exc:
        return [f"{directory.name}: {exc}"]
    module = _module_for(manifest)
    module_path = directory / (module.rsplit(".", 1)[-1] + ".py")
    if not module_path.exists():
        errors.append(f"{directory.name}: entrypoint module not found: {module_path.name}")
    for path in sorted(directory.rglob("*.py")):
        rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path.name
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            errors.append(f"{rel}: syntax error: {exc.msg}")
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".", 1)[0] in FORBIDDEN:
                    errors.append(
                        f"{rel}:{node.lineno}: plugin imports core internal {name}"
                    )
    return errors


def main() -> int:
    errors = []
    manifests = sorted(PLUGIN_DIR.glob("*/plugin.toml"))
    if not manifests:
        errors.append("no plugins found")
    for manifest in manifests:
        errors.extend(check_plugin(manifest.parent))
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        return 1
    print(f"plugins={len(manifests)} errors=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
