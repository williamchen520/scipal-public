#!/usr/bin/env python3
"""Validate the CodeRAG task fixture schema."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def validate(tasks_path: Path) -> list[str]:
    errors = []
    seen = set()
    rows = [json.loads(line) for line in tasks_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    for index, row in enumerate(rows, 1):
        task_id = row.get("task_id")
        if not task_id:
            errors.append(f"row {index}: task_id required")
        elif task_id in seen:
            errors.append(f"row {index}: duplicate task_id {task_id}")
        seen.add(task_id)
        repo = Path(row.get("repo") or "")
        if not repo.is_dir():
            errors.append(f"{task_id}: repo not found: {repo}")
            continue
        targets = row.get("target_paths") or []
        if not targets:
            errors.append(f"{task_id}: target_paths required")
        for target in targets:
            path = (repo / target).resolve()
            if repo.resolve() not in path.parents and path != repo.resolve():
                errors.append(f"{task_id}: target outside repo: {target}")
            elif not path.exists():
                errors.append(f"{task_id}: target missing: {target}")
        module = str(row.get("test_module") or "")
        if not module:
            errors.append(f"{task_id}: test_module required")
        elif not (repo / (module.replace(".", "/") + ".py")).is_file():
            errors.append(f"{task_id}: test module missing: {module}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", default="eval/code_rag_tasks.jsonl")
    args = parser.parse_args()
    errors = validate(Path(args.tasks))
    for error in errors:
        print(f"ERROR {error}")
    print(f"tasks={len(Path(args.tasks).read_text(encoding='utf-8').splitlines())} errors={len(errors)}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
