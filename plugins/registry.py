"""Discover and load enabled plugins."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from plugins.sdk import PluginError, PluginManifest, load_manifest, load_plugin

DEFAULT_DIR = Path(__file__).resolve().parent


def discover(root: Path = DEFAULT_DIR) -> dict[str, PluginManifest]:
    manifests: dict[str, PluginManifest] = {}
    for path in sorted(root.glob("*/plugin.toml")):
        manifest = load_manifest(path)
        if manifest.plugin_id in manifests:
            raise PluginError(f"duplicate plugin id: {manifest.plugin_id}")
        manifests[manifest.plugin_id] = manifest
    return manifests


def enabled_plugins() -> set[str] | None:
    raw = os.environ.get("SCIPAL_PLUGINS")
    if raw is None:
        return None
    if raw.strip().lower() in {"", "none", "off", "0"}:
        return set()
    return {item.strip() for item in raw.split(",") if item.strip()}


def load_enabled(app: Any, *, root: Path = DEFAULT_DIR, enabled: set[str] | None = None) -> list[str]:
    requested = enabled if enabled is not None else enabled_plugins()
    manifests = discover(root)
    if requested is None:
        requested = {plugin_id for plugin_id, manifest in manifests.items() if manifest.enabled}
    if not requested:
        return []
    missing = sorted(requested - set(manifests))
    if missing:
        raise PluginError(f"enabled plugins not found: {', '.join(missing)}")
    loaded = []
    for plugin_id in sorted(requested):
        load_plugin(manifests[plugin_id], app, root)
        loaded.append(plugin_id)
    return loaded
