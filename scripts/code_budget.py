#!/usr/bin/env python3
"""Count production code against the Solo Lite budget.

Production excludes tests, eval, scripts, self-check, vendor and generated files.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "docs/architecture/code-budget.json"


def _excluded(path: Path, config: dict) -> bool:
    parts = set(path.parts)
    if any(part in config.get("exclude_parts", []) for part in parts):
        return True
    return path.name in set(config.get("exclude_files", []))


def collect(root: Path, config: dict) -> dict:
    python: set[Path] = set()
    for rel in config.get("python_roots", []):
        path = root / rel
        if path.is_file() and path.suffix == ".py":
            python.add(path)
        elif path.is_dir():
            python.update(path.rglob("*.py"))
    for pattern in config.get("python_globs", []):
        python.update(root.glob(pattern))
    frontend: set[Path] = set()
    extensions = {item.lower() for item in config.get("frontend_extensions", [])}
    for rel in config.get("frontend_roots", []):
        path = root / rel
        if path.is_dir():
            frontend.update(
                item for item in path.rglob("*")
                if item.is_file() and item.suffix.lower() in extensions
            )
    files = [item for item in python | frontend if not _excluded(item, config)]
    groups: dict[str, int] = {}
    total = 0
    for item in files:
        try:
            lines = len(item.read_text(encoding="utf-8", errors="ignore").splitlines())
        except OSError:
            continue
        rel = item.relative_to(root)
        group = rel.parts[0] if len(rel.parts) > 1 else rel.name
        groups[group] = groups.get(group, 0) + lines
        total += lines
    return {"files": len(files), "lines": total, "groups": dict(sorted(groups.items()))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--check", action="store_true", help="exit 1 over limit")
    parser.add_argument("--strict", action="store_true", help="exit 1 at warning")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    result = collect(ROOT, config)
    limit = int(config.get("limit", 150000))
    warning = int(config.get("warning", 140000))
    status = "over" if result["lines"] > limit else "warning" if result["lines"] >= warning else "ok"
    result.update({"limit": limit, "warning": warning, "status": status})
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"production_lines={result['lines']} files={result['files']} status={status}")
        print(f"warning={warning} limit={limit}")
        for group, lines in result["groups"].items():
            print(f"{group:24} {lines:7}")
    if args.strict:
        return 0 if status == "ok" else 1
    if args.check:
        return 0 if status != "over" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
