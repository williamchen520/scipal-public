#!/usr/bin/env python3
"""Check generated contract artifacts and their provenance headers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from spec_compile import OUT_REL, ContractError, check

ROOT = Path(__file__).resolve().parent.parent


def header_problems(root: Path) -> list[str]:
    out = root / OUT_REL
    problems: list[str] = []
    for path in sorted(out.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"invalid JSON: {path.relative_to(root).as_posix()}: {exc}")
            continue
        generated = data.get("_generated") if isinstance(data, dict) else None
        if not isinstance(generated, dict):
            problems.append(f"missing _generated header: {path.relative_to(root).as_posix()}")
            continue
        if generated.get("do_not_edit") is not True:
            problems.append(f"_generated.do_not_edit is not true: {path.relative_to(root).as_posix()}")
        if not generated.get("source_sha256"):
            problems.append(f"missing source hash: {path.relative_to(root).as_posix()}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--check", action="store_true", help="compatibility alias; always checks")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        problems = check(root) + header_problems(root)
    except ContractError as exc:
        print(f"CONTRACT_FAIL {exc}", file=sys.stderr)
        return 1
    if problems:
        for problem in problems:
            print(f"CONTRACT_FAIL {problem}", file=sys.stderr)
        return 1
    print("CONTRACT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
