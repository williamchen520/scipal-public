#!/usr/bin/env python3
"""Join blind anchor labels with experiment metrics and summarize by anchor_type."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

ANCHOR_TYPES = {"entity", "paper", "measurement", "method", "overview"}
LABEL_FIELDS = ("anchor_type", "anchor_type_source", "annotator", "notes")


def summarize(rows: list[dict]) -> dict:
    blank = sum(1 for row in rows if not (row.get("anchor_type") or "").strip())
    invalid = sorted({
        (row.get("anchor_type") or "").strip()
        for row in rows
        if (row.get("anchor_type") or "").strip() and (row.get("anchor_type") or "").strip() not in ANCHOR_TYPES
    })
    groups: dict[str, dict] = defaultdict(lambda: {"n": 0, "base": 0.0, "fixed": 0.0, "delta": 0.0})
    for row in rows:
        anchor = (row.get("anchor_type") or "").strip()
        if anchor not in ANCHOR_TYPES:
            continue
        item = groups[anchor]
        item["n"] += 1
        item["base"] += float(row.get("baseline_ndcg") or 0.0)
        item["fixed"] += float(row.get("fixed_ndcg") or 0.0)
        item["delta"] += float(row.get("delta_ndcg") or 0.0)
    grouped = {
        key: {
            "n": value["n"],
            "baseline_ndcg": round(value["base"] / value["n"], 4),
            "fixed_ndcg": round(value["fixed"] / value["n"], 4),
            "delta_ndcg": round(value["delta"] / value["n"], 4),
        }
        for key, value in sorted(groups.items())
    }
    sources = defaultdict(int)
    for row in rows:
        sources[(row.get("anchor_type_source") or "").strip() or "blank"] += 1
    return {
        "rows": len(rows),
        "unlabeled": blank,
        "invalid": invalid,
        "sources": dict(sources),
        "groups": grouped,
        "ready": blank == 0 and not invalid,
    }


def join_labels(metrics: list[dict], labels: list[dict]) -> list[dict]:
    by_id = {row["question_id"]: row for row in labels}
    joined = []
    for row in metrics:
        label = by_id.get(row["question_id"]) or {}
        item = dict(row)
        for field in LABEL_FIELDS:
            item[field] = label.get(field, "")
        joined.append(item)
    return joined


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", default="artifacts/s1-failure-taxonomy.csv")
    parser.add_argument("--labels", default="eval/annotations/s1_anchor_sheet.csv")
    parser.add_argument("--require-human", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    metrics = list(csv.DictReader(Path(args.metrics).open(encoding="utf-8-sig", newline="")))
    labels = list(csv.DictReader(Path(args.labels).open(encoding="utf-8-sig", newline="")))
    result = summarize(join_labels(metrics, labels))
    if args.require_human:
        result["ready"] = result["ready"] and set(result["sources"]) <= {"human"}
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
