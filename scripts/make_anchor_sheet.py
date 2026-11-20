#!/usr/bin/env python3
"""Create a blind anchor annotation sheet (questions only, no metrics)."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

FIELDS = ["question_id", "question", "anchor_type", "anchor_type_source", "annotator", "notes"]


def make_sheet(questions_path: Path, out_path: Path, *, force: bool = False) -> int:
    rows = [
        json.loads(line)
        for line in questions_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if out_path.exists() and not force:
        raise FileExistsError(f"{out_path} exists; refusing to overwrite labels")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "question_id": row["question_id"],
                "question": row["question"],
                "anchor_type": "",
                "anchor_type_source": "",
                "annotator": "",
                "notes": "",
            })
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", default="eval/s1_internal_questions.jsonl")
    parser.add_argument("--out", default="eval/annotations/s1_anchor_sheet.csv")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        count = make_sheet(Path(args.questions), Path(args.out), force=args.force)
    except FileExistsError as exc:
        print(f"ERROR {exc}")
        return 1
    print(f"rows={count} out={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
