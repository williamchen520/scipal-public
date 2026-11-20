#!/usr/bin/env python3
"""Check production import boundaries with AST (no imports executed)."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_PARTS = {"venv_sciPal_py312", ".git", "__pycache__", "site-packages", "tests"}

RULES = {
    "code_rag": {"routes", "services", "api_server", "build_db"},
    "services": {"routes", "api_server"},
    "routes": {"api_server"},
    "build_db": {"routes", "api_server"},
}


def module_name(path: Path, root: Path = ROOT) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def imported_roots(path: Path, tree: ast.AST, root: Path = ROOT) -> set[str]:
    roots: set[str] = set()
    package = module_name(path, root).split(".")[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                keep = max(0, len(package) - node.level + 1)
                base = ".".join(package[:keep] + ([base] if base else []))
            if base:
                roots.add(base.split(".")[0])
    return roots


def check(root: Path = ROOT) -> list[dict]:
    violations = []
    for path in root.rglob("*.py"):
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        module = module_name(path, root)
        top = module.split(".")[0]
        forbidden = RULES.get(top)
        if not forbidden:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for imported in sorted(imported_roots(path, tree, root)):
            if imported in forbidden:
                violations.append(
                    {"module": module, "imports": imported, "file": str(path.relative_to(root))}
                )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="exit 1 on violations")
    args = parser.parse_args()
    violations = check()
    if args.json:
        print(json.dumps({"violations": violations, "count": len(violations)}, ensure_ascii=False, indent=2))
    else:
        for item in violations:
            print(f"VIOLATION {item['module']} imports {item['imports']} ({item['file']})")
        print(f"violations={len(violations)}")
    if args.strict and violations:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
