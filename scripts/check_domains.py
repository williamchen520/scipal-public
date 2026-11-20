#!/usr/bin/env python3
"""Validate domain ownership, paths, and dependency acyclicity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / "docs/architecture/domains.json"


def check(path: Path = DEFAULT, root: Path = ROOT) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    domains = data.get("domains")
    if not isinstance(domains, list) or not domains:
        return ["domains must be a non-empty list"]
    errors: list[str] = []
    ids: dict[str, dict] = {}
    paths: set[str] = set()
    for domain in domains:
        domain_id = str(domain.get("id") or "").strip()
        if not domain_id:
            errors.append("domain without id")
            continue
        if domain_id in ids:
            errors.append(f"duplicate domain: {domain_id}")
        ids[domain_id] = domain
        if not str(domain.get("owner") or "").strip():
            errors.append(f"domain {domain_id} has no owner")
        domain_paths = domain.get("paths") or []
        if not domain_paths:
            errors.append(f"domain {domain_id} has no paths")
        for rel in domain_paths:
            rel = str(rel)
            if rel in paths:
                errors.append(f"path claimed by multiple domains: {rel}")
            paths.add(rel)
            if not (root / rel).exists():
                errors.append(f"domain {domain_id} path missing: {rel}")
        for rel in domain.get("tests") or []:
            if not (root / str(rel)).exists():
                errors.append(f"domain {domain_id} test missing: {rel}")
    for domain_id, domain in ids.items():
        for dep in domain.get("depends_on") or []:
            if dep not in ids:
                errors.append(f"domain {domain_id} depends on unknown: {dep}")
            if dep == domain_id:
                errors.append(f"domain {domain_id} depends on itself")
    # DFS cycle check
    state: dict[str, int] = {}

    def visit(node: str) -> None:
        if state.get(node) == 1:
            errors.append(f"domain dependency cycle at {node}")
            return
        if state.get(node) == 2:
            return
        state[node] = 1
        for dep in ids[node].get("depends_on") or []:
            if dep in ids:
                visit(dep)
        state[node] = 2

    for domain_id in ids:
        visit(domain_id)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domains", default=str(DEFAULT))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    errors = check(Path(args.domains))
    data = json.loads(Path(args.domains).read_text(encoding="utf-8"))
    result = {"domains": len(data.get("domains") or []), "errors": errors, "ok": not errors}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"domains={result['domains']} errors={len(errors)}")
        for error in errors:
            print(f"ERROR {error}")
        print("OK" if not errors else "FAILED")
    return 0 if not errors or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
