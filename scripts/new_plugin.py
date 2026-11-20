#!/usr/bin/env python3
"""Scaffold a disabled-by-default SciPal plugin."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

PLUGIN_ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


def scaffold(plugin_id: str, dest: Path, *, force: bool = False) -> Path:
    if not PLUGIN_ID.match(plugin_id):
        raise ValueError("plugin id must match ^[a-z][a-z0-9_]{1,63}$")
    target = dest / plugin_id
    if target.exists() and any(target.iterdir()) and not force:
        raise ValueError(f"target already exists and is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    (target / "__init__.py").write_text("", encoding="utf-8")
    (target / "plugin.toml").write_text(
        f'id = "{plugin_id}"\n'
        'version = "0.1.0"\n'
        'core_api = "1"\n'
        f'entrypoint = "plugins.{plugin_id}.plugin:register"\n'
        "enabled = false\n"
        'description = "TODO"\n',
        encoding="utf-8",
    )
    (target / "plugin.py").write_text(
        "from __future__ import annotations\n\n"
        "from flask import Blueprint\n\n\n"
        "def register(ctx):\n"
        f'    bp = Blueprint("{plugin_id}", __name__, url_prefix="/api/{plugin_id}")\n\n'
        f'    @bp.get("/health")\n'
        "    def health():\n"
        f'        return {{"ok": True, "plugin": "{plugin_id}"}}\n\n'
        "    return bp\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True)
    parser.add_argument("--dest", default="plugins")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    target = scaffold(args.id, Path(args.dest), force=args.force)
    print(f"created {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
