"""Pre-registered evaluation spec validation and hashing."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REQUIRED = (
    "id",
    "metric",
    "dataset",
    "corpus",
    "split",
    "sample_size",
    "baseline",
    "external_anchor",
    "heldout",
    "owner",
    "reviewer",
    "decision_rule",
)
POSITIVE = ("sample_size",)


def validate(spec: dict[str, Any]) -> list[str]:
    errors = [
        f"missing:{field}" for field in REQUIRED if not str(spec.get(field) or "").strip()
    ]
    for field in POSITIVE:
        value = spec.get(field)
        if not isinstance(value, int) or value <= 0:
            errors.append(f"invalid:{field}")
    if spec.get("threshold") is not None and not str(spec.get("threshold_basis") or "").strip():
        errors.append("threshold_without_basis")
    if spec.get("baseline") == spec.get("candidate"):
        errors.append("baseline_equals_candidate")
    return sorted(set(errors))


def canonical_hash(spec: dict[str, Any]) -> str:
    payload = json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("spec must be a JSON object")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("spec")
    parser.add_argument("--hash", action="store_true")
    parser.add_argument("--write-hash", default="")
    args = parser.parse_args()
    spec = load(args.spec)
    errors = validate(spec)
    digest = canonical_hash(spec)
    if errors:
        print("EVAL_SPEC_INVALID " + ",".join(errors))
        return 2
    if args.write_hash:
        Path(args.write_hash).write_text(digest + "\n", encoding="utf-8")
    print(f"EVAL_SPEC_OK id={spec['id']} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
