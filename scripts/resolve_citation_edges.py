#!/usr/bin/env python3
"""Resolve citation edges whose destination now exists locally."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.papers.citations import resolve_local_destinations  # noqa: E402


def main() -> int:
    print(json.dumps(resolve_local_destinations(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
