#!/usr/bin/env python3
"""Release-time runtime contract gate.

This imports the real Flask app and compares it with ARCHITECTURE.json.
It is intentionally not part of the default CI: importing api_server needs
deployment DSNs. Run it in the release environment, before tagging.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = ROOT / "scripts" / "validate_arch.py"
REQUIRED_ENV = ("SCIPAL_AUTH_DSN", "SCIPAL_CORE_DSN", "SCIPAL_PG_DSN")


def missing_env() -> list[str]:
    return [name for name in REQUIRED_ENV if not os.environ.get(name)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", default=str(ROOT / "ARCHITECTURE.json"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    missing = missing_env()
    if missing:
        print("RUNTIME_CONTRACT_SKIP missing env: " + ", ".join(missing), file=sys.stderr)
        print("Set the deployment DSNs, then rerun before tagging.", file=sys.stderr)
        return 2

    command = [
        sys.executable,
        str(VALIDATOR),
        "--arch",
        args.arch,
        "--json",
    ]
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if completed.returncode != 0:
        print("RUNTIME_CONTRACT_FAIL " + (completed.stderr.strip() or completed.stdout.strip()))
        return 1
    text = completed.stdout
    start = text.find("{")
    try:
        result = json.loads(text[start:]) if start >= 0 else {}
    except json.JSONDecodeError:
        print("RUNTIME_CONTRACT_FAIL validator did not return JSON")
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"RUNTIME_CONTRACT_OK json_routes={result.get('json_routes')} "
            f"app_routes={result.get('app_routes')} framework={result.get('framework')}"
        )
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
