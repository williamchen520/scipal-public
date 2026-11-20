#!/usr/bin/env python3
"""Run unittest and write a machine-readable duration artifact."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pattern", default="test_*.py")
    parser.add_argument("--output", default="artifacts/test-duration.json")
    args = parser.parse_args()
    started = time.perf_counter()
    code = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", args.pattern],
        cwd=ROOT,
    ).returncode
    elapsed = round(time.perf_counter() - started, 3)
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {"duration_seconds": elapsed, "status": "pass" if code == 0 else "fail",
             "pattern": args.pattern, "exit_code": code},
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"TEST_DURATION seconds={elapsed} status={'pass' if code == 0 else 'fail'} output={output}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
