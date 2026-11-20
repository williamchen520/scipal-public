#!/usr/bin/env python3
"""Export citation edges from scipal_rebuild for relation experiments."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def normalize_doi(value: str) -> str:
    text = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", (value or "").strip(), flags=re.I)
    return text.lower()


def cited_node(doi: str, title: str) -> str:
    doi = normalize_doi(doi)
    if doi:
        return f"doi:{doi}"
    clean = re.sub(r"\W+", " ", (title or "").lower()).strip()
    if clean:
        return "title:" + hashlib.sha1(clean.encode("utf-8")).hexdigest()[:16]
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--out", default="artifacts/relation-edges.jsonl")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    import psycopg

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    edges = 0
    citations = 0
    with psycopg.connect(args.dsn) as conn, out.open("w", encoding="utf-8") as handle:
        query = "SELECT paper_id,doi,title,ref_number FROM citations ORDER BY paper_id,ref_number"
        if args.limit > 0:
            query += f" LIMIT {int(args.limit)}"
        for citing, doi, title, ref_number in conn.execute(query):
            citations += 1
            cited = cited_node(doi or "", title or "")
            if not citing or not cited or citing == cited:
                continue
            key = (citing, cited)
            if key in seen:
                continue
            seen.add(key)
            handle.write(json.dumps({
                "citing_id": citing,
                "cited_id": cited,
                "ref_number": str(ref_number or ""),
            }, ensure_ascii=False) + "\n")
            edges += 1
    print(f"citations={citations} edges={edges} out={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
