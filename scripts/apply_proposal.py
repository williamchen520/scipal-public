#!/usr/bin/env python3
"""Apply an approved implementation proposal to a local worktree.

This is a client-side, human-approved write. It never executes code.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from code_rag.implement import validate_files


def apply_proposal(path: Path, root: Path, *, approve: bool) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    files = data.get("files") or []
    errors = validate_files(files)
    if errors:
        raise SystemExit("; ".join(errors))
    root = root.resolve()
    targets = []
    for item in files:
        target = (root / item["path"]).resolve()
        if root not in target.parents and target != root:
            raise SystemExit(f"refusing path outside root: {item['path']}")
        targets.append((target, item["content"]))
    if not approve:
        for target, _ in targets:
            print(f"WOULD_WRITE {target}")
        print("not applied; pass --approve")
        return [str(target) for target, _ in targets]
    for target, content in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".proposal_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        print(f"WROTE {target}")
    return [str(target) for target, _ in targets]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--approve", action="store_true")
    args = parser.parse_args()
    apply_proposal(Path(args.proposal), Path(args.root), approve=args.approve)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
