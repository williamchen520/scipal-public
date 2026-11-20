"""Minimal plugin contract: manifest, context, load/register."""

from __future__ import annotations

import importlib
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

PLUGIN_ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
CORE_API = "1"


class PluginError(RuntimeError):
    pass


@dataclass(frozen=True)
class PluginManifest:
    plugin_id: str
    version: str
    core_api: str
    entrypoint: str
    description: str = ""
    enabled: bool = False
    directory: Path | None = None


@dataclass
class PluginContext:
    app: Any
    root: Path
    manifest: PluginManifest


def load_manifest(path: Path) -> PluginManifest:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    plugin_id = str(data.get("id") or "").strip()
    version = str(data.get("version") or "").strip()
    core_api = str(data.get("core_api") or "").strip()
    entrypoint = str(data.get("entrypoint") or "").strip()
    if not PLUGIN_ID.match(plugin_id):
        raise PluginError(f"invalid plugin id: {plugin_id!r}")
    if not version:
        raise PluginError(f"{plugin_id}: version is required")
    if core_api != CORE_API:
        raise PluginError(f"{plugin_id}: core_api must be {CORE_API}")
    if ":" not in entrypoint:
        raise PluginError(f"{plugin_id}: entrypoint must be module:callable")
    return PluginManifest(
        plugin_id=plugin_id,
        version=version,
        core_api=core_api,
        entrypoint=entrypoint,
        description=str(data.get("description") or ""),
        enabled=bool(data.get("enabled", False)),
        directory=path.parent,
    )


def load_plugin(manifest: PluginManifest, app: Any, root: Path | None = None) -> Any:
    module_name, _, attr = manifest.entrypoint.partition(":")
    try:
        module = importlib.import_module(module_name)
        register: Callable[[PluginContext], Any] = getattr(module, attr)
    except (ImportError, AttributeError) as exc:
        raise PluginError(f"{manifest.plugin_id}: cannot load {manifest.entrypoint}") from exc
    context = PluginContext(app=app, root=root or Path.cwd(), manifest=manifest)
    result = register(context)
    if result is not None:
        app.register_blueprint(result)
    return result
