#!/usr/bin/env python3
"""Compile contract/spec.json into deterministic spec_exec artifacts.

The compiler only translates machine-checkable rules. It does not decide
research questions, approve exceptions, or generate application code.
"""

from __future__ import annotations

import argparse
import ast
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SPEC_REL = Path("contract/spec.json")
OUT_REL = Path("spec_exec")


class ContractError(RuntimeError):
    pass


TEXT_SUFFIXES = {".json", ".md", ".py", ".yml", ".yaml", ".txt", ".cff"}


def sha256(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.lower() in TEXT_SUFFIXES:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON: {path}: {exc}") from exc


def generated_header(source: Path, root: Path) -> dict[str, Any]:
    return {
        "generated_by": "scripts/spec_compile.py",
        "source": source.relative_to(root).as_posix(),
        "source_sha256": sha256(source),
        "do_not_edit": True,
    }


def route_key(endpoint: dict[str, Any]) -> str:
    methods = sorted(str(m).upper() for m in (endpoint.get("methods") or ["GET"]))
    return f"{endpoint.get('rule', '')} {'|'.join(methods)}"


SUPPORTED_KINDS = {"architecture_json", "route_unique", "required_paths", "stdlib_only", "runtime_contract"}


def load_approval(
    root: Path, spec: dict[str, Any], spec_path: Path
) -> tuple[dict[str, Any], list[str]]:
    rel = Path(str(spec.get("approval", "contract/approval.json")))
    path = root / rel
    if not path.is_file():
        return {}, [f"missing spec approval: {rel.as_posix()}"]
    try:
        data = read_json(path)
    except ContractError as exc:
        return {}, [str(exc)]
    errors: list[str] = []
    if data.get("schema_version") != 1:
        errors.append(f"{rel.as_posix()}: schema_version must be 1")
    if str(data.get("approved_by", "")).lower() != "human":
        errors.append(f"{rel.as_posix()}: approved_by must be human")
    if not str(data.get("approved_on", "")).strip():
        errors.append(f"{rel.as_posix()}: missing approved_on")
    approved_hash = str(data.get("spec_sha256", ""))
    actual_hash = sha256(spec_path)
    if approved_hash != actual_hash:
        errors.append(
            f"spec approval mismatch: {rel.as_posix()} does not approve the current contract/spec.json"
        )
    return data, errors


def check_runtime_contract(root: Path, rule: dict[str, Any]) -> list[str]:
    fixture_rel = Path(str(rule.get("fixture_root", "contract/runtime_fixture")))
    fixture = root / fixture_rel
    arch_rel = Path(str(rule.get("architecture", str(fixture_rel / "architecture.json"))))
    arch = root / arch_rel
    app_root = root / Path(str(rule.get("root", str(fixture_rel))))
    validator = root / "scripts" / "validate_arch.py"
    if not arch.is_file():
        return [f"runtime_contract: missing {arch.relative_to(root).as_posix()}"]
    if not validator.is_file():
        return ["runtime_contract: missing scripts/validate_arch.py"]
    command = [
        sys.executable,
        str(validator),
        "--arch",
        str(arch),
        "--app",
        str(rule.get("app", "app:app")),
        *(["--root", str(app_root)] if rule.get("root_arg", True) else []),
        "--json",
    ]
    try:
        completed = subprocess.run(
            command, cwd=root, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [f"runtime_contract: could not run validate_arch.py: {exc}"]
    if completed.returncode != 0:
        return [
            "runtime_contract: validate_arch.py failed: "
            + (completed.stderr.strip() or completed.stdout.strip())[:500]
        ]
    text = completed.stdout
    start = text.find("{")
    try:
        result = json.loads(text[start:]) if start >= 0 else {}
    except json.JSONDecodeError:
        return ["runtime_contract: validate_arch.py did not return JSON"]
    errors = result.get("errors") or []
    if not result.get("ok") or errors:
        return ["runtime_contract: " + str(error) for error in errors] or [
            "runtime_contract: fixture app does not match its contract"
        ]
    return []


def load_exceptions(root: Path, spec: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    rel = Path(str(spec.get("exceptions", "contract/exceptions.json")))
    path = root / rel
    if not path.is_file():
        return [], []
    try:
        data = read_json(path)
    except ContractError as exc:
        return [], [str(exc)]
    if data.get("schema_version") != 1:
        return [], [f"{rel.as_posix()}: schema_version must be 1"]
    entries = data.get("exceptions")
    if not isinstance(entries, list):
        return [], [f"{rel.as_posix()}: exceptions must be a list"]

    today = datetime.date.today()
    active: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append(f"{rel.as_posix()}: each exception must be an object")
            continue
        exc_id = str(entry.get("id", ""))
        rule_id = str(entry.get("rule", ""))
        target = str(entry.get("target", ""))
        if not exc_id or not rule_id or not target:
            errors.append(f"{rel.as_posix()}: exception needs id, rule, target")
            continue
        if exc_id in seen:
            errors.append(f"{rel.as_posix()}: duplicate exception id {exc_id}")
            continue
        seen.add(exc_id)
        if "*" in target or "?" in target:
            errors.append(f"{rel.as_posix()}: wildcard target is not allowed: {exc_id}")
            continue
        if str(entry.get("approved_by", "")).lower() != "human":
            errors.append(f"{rel.as_posix()}: approved_by must be human: {exc_id}")
            continue
        if len(str(entry.get("reason", "")).strip()) < 10:
            errors.append(f"{rel.as_posix()}: reason too short: {exc_id}")
            continue
        try:
            approved_on = datetime.date.fromisoformat(str(entry.get("approved_on", "")))
            expires_on = datetime.date.fromisoformat(str(entry.get("expires_on", "")))
        except ValueError:
            errors.append(f"{rel.as_posix()}: invalid ISO date: {exc_id}")
            continue
        if expires_on < approved_on:
            errors.append(f"{rel.as_posix()}: expires before approval: {exc_id}")
            continue
        if expires_on < today:
            errors.append(f"{rel.as_posix()}: expired exception: {exc_id}")
            continue
        active.append(
            {
                "id": exc_id,
                "rule": rule_id,
                "target": target,
                "reason": str(entry.get("reason", "")),
                "approved_by": "human",
                "approved_on": approved_on.isoformat(),
                "expires_on": expires_on.isoformat(),
            }
        )
    return active, errors


def find_exception(
    active: list[dict[str, Any]], rule_id: str, target: str, used: set[str]
) -> dict[str, Any] | None:
    for entry in active:
        if entry["rule"] == rule_id and entry["target"] == target:
            used.add(entry["id"])
            return entry
    return None


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def check_stdlib_only(root: Path, rule: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    allowed = set(sys.stdlib_module_names) | set(rule.get("allow", []))
    for rel in rule.get("paths", []):
        path = root / str(rel)
        if not path.is_file():
            errors.append(f"stdlib_only: missing file {rel}")
            continue
        try:
            roots = _imported_roots(path)
        except (OSError, SyntaxError) as exc:
            errors.append(f"stdlib_only: cannot parse {rel}: {exc}")
            continue
        for name in sorted(roots - allowed):
            errors.append(f"stdlib_only: non-stdlib import {name!r} in {rel}")
    return errors


def load_required_paths(spec: dict[str, Any], root: Path) -> list[str]:
    paths: list[str] = []
    for rule in spec.get("rules", []):
        if rule.get("kind") == "required_paths":
            paths.extend(str(p) for p in rule.get("paths", []))
    return paths


def build_artifacts(root: Path) -> tuple[dict[str, str], list[str]]:
    spec_path = root / SPEC_REL
    spec = read_json(spec_path)
    errors: list[str] = []
    approval, approval_errors = load_approval(root, spec, spec_path)
    errors.extend(approval_errors)

    if spec.get("schema_version") != 1:
        errors.append("contract/spec.json: schema_version must be 1")
    if not isinstance(spec.get("rules"), list) or not spec.get("rules"):
        errors.append("contract/spec.json: rules must be a non-empty list")

    coverage: list[dict[str, Any]] = []
    seen_rule_ids: set[str] = set()
    for rule in spec.get("rules", []):
        if not isinstance(rule, dict):
            errors.append("contract/spec.json: each rule must be an object")
            continue
        rule_id = str(rule.get("id", ""))
        kind = str(rule.get("kind", ""))
        check_name = str(rule.get("check", ""))
        if not rule_id:
            errors.append("contract/spec.json: rule missing id")
        elif rule_id in seen_rule_ids:
            errors.append(f"contract/spec.json: duplicate rule id {rule_id}")
        seen_rule_ids.add(rule_id)
        if kind not in SUPPORTED_KINDS:
            errors.append(f"contract/spec.json: unsupported kind {kind!r} for {rule_id}")
        if not check_name:
            errors.append(f"contract/spec.json: missing check for {rule_id}")
        covered = kind in SUPPORTED_KINDS and bool(check_name)
        coverage.append({"id": rule_id, "kind": kind, "check": check_name, "covered": covered})
        if kind == "stdlib_only":
            errors.extend(check_stdlib_only(root, rule))
        if kind == "runtime_contract":
            errors.extend(check_runtime_contract(root, rule))

    active_exceptions, exception_errors = load_exceptions(root, spec)
    errors.extend(exception_errors)
    used_exceptions: set[str] = set()
    suppressed: list[dict[str, Any]] = []

    arch_rel = Path(str(spec.get("architecture", "ARCHITECTURE.json")))
    arch_path = root / arch_rel
    try:
        arch = read_json(arch_path)
    except ContractError as exc:
        errors.append(str(exc))
        arch = {}

    endpoints: list[dict[str, Any]] = []
    api = arch.get("api") if isinstance(arch, dict) else None
    if not isinstance(api, dict) or not isinstance(api.get("endpoints"), list):
        errors.append(f"{arch_rel}: api.endpoints must be a list")
    else:
        endpoints = [e for e in api["endpoints"] if isinstance(e, dict)]

    seen: dict[str, int] = {}
    for endpoint in endpoints:
        key = route_key(endpoint)
        seen[key] = seen.get(key, 0) + 1
    raw_duplicates = sorted(key for key, count in seen.items() if count > 1)
    duplicates: list[str] = []
    for key in raw_duplicates:
        exc = find_exception(active_exceptions, "architecture.route_unique", key, used_exceptions)
        if exc:
            suppressed.append({"exception": exc["id"], "rule": "architecture.route_unique", "target": key})
        else:
            duplicates.append(key)
    if duplicates:
        errors.append("ARCHITECTURE.json: duplicate route+method: " + ", ".join(duplicates))

    required = load_required_paths(spec, root)
    layout = [
        {"path": path, "exists": (root / path).is_file()}
        for path in required
    ]
    raw_missing = [item["path"] for item in layout if not item["exists"]]
    missing: list[str] = []
    for path in raw_missing:
        exc = find_exception(active_exceptions, "repo.required_paths", path, used_exceptions)
        if exc:
            suppressed.append({"exception": exc["id"], "rule": "repo.required_paths", "target": path})
        else:
            missing.append(path)
    if missing:
        errors.append("missing required paths: " + ", ".join(missing))

    unused = sorted(entry["id"] for entry in active_exceptions if entry["id"] not in used_exceptions)
    if unused:
        errors.append("unused exceptions: " + ", ".join(unused))

    header = generated_header(spec_path, root)
    manifest = {
        "_generated": header,
        "schema_version": spec.get("schema_version"),
        "name": spec.get("name"),
        "source_commit": spec.get("source_commit"),
        "spec_approval": {
            "approved_by": approval.get("approved_by"),
            "approved_on": approval.get("approved_on"),
            "spec_sha256": approval.get("spec_sha256"),
        },
        "exceptions_file": spec.get("exceptions", "contract/exceptions.json"),
        "active_exceptions": len(active_exceptions),
        "rules": [
            {
                "id": rule.get("id"),
                "kind": rule.get("kind"),
                "severity": rule.get("severity"),
                "owner": rule.get("owner"),
                "approval": rule.get("approval"),
                "check": rule.get("check"),
            }
            for rule in spec.get("rules", [])
            if isinstance(rule, dict)
        ],
        "source_files": [
            {"path": SPEC_REL.as_posix(), "sha256": sha256(spec_path)},
            {"path": arch_rel.as_posix(), "sha256": sha256(arch_path)}
            if arch_path.is_file()
            else {"path": arch_rel.as_posix(), "sha256": None},
        ],
    }
    architecture_contract = {
        "_generated": header,
        "architecture": arch_rel.as_posix(),
        "endpoint_count": len(endpoints),
        "endpoints": [
            {
                "rule": endpoint.get("rule"),
                "methods": sorted(str(m).upper() for m in (endpoint.get("methods") or ["GET"])),
                "status": endpoint.get("status", "implemented"),
            }
            for endpoint in endpoints
        ],
        "duplicate_routes": duplicates,
    }
    repo_layout = {
        "_generated": header,
        "required_paths": layout,
        "missing": missing,
    }
    coverage_doc = {
        "_generated": header,
        "rules": coverage,
        "all_covered": all(item["covered"] for item in coverage),
    }
    exception_doc = {
        "_generated": header,
        "active": active_exceptions,
        "suppressed": suppressed,
        "used": sorted(used_exceptions),
    }
    artifacts = {
        "manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        "architecture_contract.json": json.dumps(
            architecture_contract, ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
        "repo_layout.json": json.dumps(repo_layout, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        "coverage.json": json.dumps(coverage_doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        "exceptions.json": json.dumps(exception_doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    }
    return artifacts, errors


def check(root: Path) -> list[str]:
    artifacts, errors = build_artifacts(root)
    if errors:
        return errors
    out = root / OUT_REL
    problems: list[str] = []
    if not out.is_dir():
        return [f"missing generated directory: {OUT_REL.as_posix()}"]
    for name, expected in artifacts.items():
        path = out / name
        if not path.is_file():
            problems.append(f"missing generated file: {path.relative_to(root).as_posix()}")
            continue
        actual = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        if actual != expected:
            problems.append(f"generated file is stale: {path.relative_to(root).as_posix()}")
    expected_names = set(artifacts)
    actual_names = {p.name for p in out.glob("*.json")}
    for name in sorted(actual_names - expected_names):
        problems.append(f"unexpected generated file: {(out / name).relative_to(root).as_posix()}")
    return problems


def write(root: Path) -> None:
    artifacts, errors = build_artifacts(root)
    if errors:
        raise ContractError("; ".join(errors))
    out = root / OUT_REL
    out.mkdir(parents=True, exist_ok=True)
    for name, content in artifacts.items():
        (out / name).write_text(content, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true", help="write spec_exec artifacts")
    group.add_argument("--check", action="store_true", help="check spec_exec is current")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        if args.check:
            problems = check(root)
            if problems:
                for problem in problems:
                    print(f"CONTRACT_FAIL {problem}", file=sys.stderr)
                return 1
            print("CONTRACT_OK")
            return 0
        write(root)
        print(f"CONTRACT_WRITTEN {OUT_REL.as_posix()}")
        return 0
    except ContractError as exc:
        print(f"CONTRACT_FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
