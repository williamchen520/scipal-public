#!/usr/bin/env python3
"""Report changed files -> affected modules, tests, and route candidates."""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_PARTS = {"venv_sciPal_py312", ".git", "__pycache__", "site-packages", "node_modules"}


def module_name(path: Path, root: Path = ROOT) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolve(base: str, modules: set[str]) -> set[str]:
    parts = base.split(".") if base else []
    while parts:
        candidate = ".".join(parts)
        if candidate in modules:
            return {candidate}
        parts.pop()
    return set()


def imports(path: Path, root: Path, modules: set[str]) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return set()
    module = module_name(path, root)
    package = module.split(".")[:-1]
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                result |= _resolve(alias.name, modules)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                keep = max(0, len(package) - node.level + 1)
                base = ".".join(package[:keep] + ([base] if base else []))
            result |= _resolve(base, modules)
            for alias in node.names:
                result |= _resolve(f"{base}.{alias.name}" if base else alias.name, modules)
    return result


def build_graph(root: Path = ROOT) -> tuple[dict[str, set[str]], dict[str, str]]:
    files = [
        path for path in root.rglob("*.py")
        if not any(part in SKIP_PARTS for part in path.parts)
    ]
    modules = {module_name(path, root) for path in files}
    graph: dict[str, set[str]] = {}
    file_of: dict[str, str] = {}
    for path in files:
        module = module_name(path, root)
        file_of[module] = str(path.relative_to(root))
        graph[module] = imports(path, root, modules)
    return graph, file_of


def reverse_graph(graph: dict[str, set[str]]) -> dict[str, set[str]]:
    reverse: dict[str, set[str]] = {module: set() for module in graph}
    for source, targets in graph.items():
        for target in targets:
            reverse.setdefault(target, set()).add(source)
    return reverse


def affected(start: set[str], graph: dict[str, set[str]]) -> set[str]:
    reverse = reverse_graph(graph)
    seen = set(start)
    queue = deque(start)
    while queue:
        current = queue.popleft()
        for dependent in reverse.get(current, set()):
            if dependent not in seen:
                seen.add(dependent)
                queue.append(dependent)
    return seen




def load_domains(root: Path = ROOT) -> list[dict]:
    path = root / "docs/architecture/domains.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("domains", [])


def domain_for_path(rel: str, domains: list[dict]) -> str:
    rel = rel.replace("\\", "/").lstrip("./")
    best = ""
    best_len = -1
    for domain in domains:
        for prefix in domain.get("paths") or []:
            prefix = str(prefix).rstrip("/")
            if rel == prefix or rel.startswith(prefix + "/"):
                if len(prefix) > best_len:
                    best = str(domain.get("id") or "")
                    best_len = len(prefix)
    return best


def contract_surfaces(changed: list[str]) -> list[str]:
    surfaces = set()
    for path in changed:
        path = path.replace("\\", "/")
        if path in {"ARCHITECTURE.json", "ARCH_CONTRACT.json"} or path.startswith("docs/architecture/generated/"):
            surfaces.add("api")
        if path == "docs/architecture/domains.json":
            surfaces.add("domain")
        if path.startswith("deploy/sql/") or path in {"deploy/migrations.lock.json"}:
            surfaces.add("schema")
        if path.startswith("services/tenancy/") or path.startswith("contracts/"):
            surfaces.add("auth")
    return sorted(surfaces)


def route_candidates(modules: set[str], route_manifest: Path) -> list[dict]:
    if not route_manifest.exists():
        return []
    data = json.loads(route_manifest.read_text(encoding="utf-8"))
    routes = data.get("routes", [])
    blueprints = {
        module.split(".")[1] for module in modules
        if module.startswith("routes.") and len(module.split(".")) > 1
    }
    return [row for row in routes if row.get("blueprint") in blueprints]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref", default="HEAD~1")
    parser.add_argument("--files", default="", help="comma-separated paths; overrides git diff")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--domains", default="docs/architecture/domains.json")
    args = parser.parse_args()
    root = Path(args.root)
    if args.files:
        changed = [item.strip() for item in args.files.split(",") if item.strip()]
    else:
        raw = subprocess.run(
            ["git", "diff", "--name-only", f"{args.base_ref}...HEAD"],
            cwd=root, capture_output=True, text=True, check=False,
        ).stdout
        changed = [line.strip() for line in raw.splitlines() if line.strip()]
    graph, file_of = build_graph(root)
    changed_modules = {
        module_name(root / item, root) for item in changed
        if item.endswith(".py") and (root / item).exists()
    }
    impacted = affected(changed_modules, graph)
    tests = sorted(module for module in impacted if module == "tests" or module.startswith("tests."))
    routes = route_candidates(impacted, root / "docs/architecture/generated/routes.json")
    domains = load_domains(root)
    changed_domains = sorted({d for p in changed if (d := domain_for_path(p, domains))})
    affected_domains = sorted({d for p in changed if (d := domain_for_path(p, domains))} | {
        d for m in impacted if (d := domain_for_path(file_of.get(m, ""), domains))
    })
    surfaces = contract_surfaces(changed)
    if "domain" in surfaces or "api" in surfaces:
        affected_domains = sorted({str(d.get("id")) for d in domains})
    domain_tests = {
        "tests." + Path(test).stem
        for d in affected_domains
        for test in (next((x.get("tests") or [] for x in domains if x.get("id") == d), []))
    }
    result = {
        "changed": changed,
        "changed_modules": sorted(changed_modules),
        "affected_modules": sorted(impacted),
        "affected_tests": tests,
        "route_candidates": routes,
        "changed_domains": changed_domains,
        "affected_domains": affected_domains,
        "contract_surfaces": surfaces,
        "required_tests": sorted(set(tests) | domain_tests),
        "counts": {
            "changed": len(changed),
            "modules": len(impacted),
            "tests": len(tests),
            "routes": len(routes),
            "domains": len(affected_domains),
        },
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"changed={len(changed)} modules={len(impacted)} tests={len(tests)} routes={len(routes)}")
        for module in sorted(impacted):
            print(f"MODULE {module} ({file_of.get(module, '')})")
        for module in tests:
            print(f"TEST {module}")
        for route in routes:
            print(f"ROUTE {route['method']} {route['rule']}")
        for domain in affected_domains:
            print(f"DOMAIN {domain}")
        for surface in contract_surfaces(changed):
            print(f"CONTRACT {surface}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
