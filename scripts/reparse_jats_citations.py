#!/usr/bin/env python3
"""Re-parse affected JATS XMLs to repair citation DOIs (dry-run by default)."""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_db.jats_parser import parse_file


def _norm(value: str) -> str:
    return re.sub(r"\W+", " ", (value or "").lower()).strip()


def _aligned(citation_title: str, ref_title: str) -> bool:
    left, right = _norm(citation_title), _norm(ref_title)
    if not left or not right:
        return True
    return left in right or right in left


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--xml-dir", default="documents_xml")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    import psycopg

    xml_dir = Path(args.xml_dir)
    scanned = changed = missing = misaligned = failed = 0
    with psycopg.connect(args.dsn) as conn:
        papers = conn.execute(
            "SELECT p.paper_id,p.filename FROM papers p WHERE p.paper_id IN "
            "(SELECT DISTINCT paper_id FROM citations WHERE doi LIKE '%(%')"
        ).fetchall()
        rows = conn.execute(
            "SELECT c.citation_id,c.paper_id,c.doi,c.title FROM citations c "
            "WHERE c.paper_id IN (SELECT DISTINCT paper_id FROM citations WHERE doi LIKE '%(%') "
            "ORDER BY c.paper_id,c.ref_number"
        ).fetchall()
        by_paper: dict[str, list[tuple]] = defaultdict(list)
        for citation_id, paper_id, doi, title in rows:
            by_paper[paper_id].append((citation_id, doi or "", title or ""))
        updates = []
        for paper_id, filename in papers:
            if args.limit and scanned >= args.limit:
                break
            path = xml_dir / str(filename or "")
            if not path.exists():
                missing += 1
                continue
            try:
                refs = parse_file(path)["references"]
            except Exception:
                failed += 1
                continue
            citations = by_paper.get(paper_id, [])
            if len(refs) != len(citations):
                misaligned += 1
                continue
            scanned += 1
            for (citation_id, old_doi, old_title), ref in zip(citations, refs):
                new_doi = (ref.get("doi") or "").strip().lower()
                if not new_doi or new_doi == old_doi.strip().lower():
                    continue
                if not _aligned(old_title, ref.get("title") or ""):
                    misaligned += 1
                    continue
                updates.append((new_doi, citation_id))
                changed += 1
            if args.apply and len(updates) >= 1000:
                with conn.cursor() as cur:
                    cur.executemany("UPDATE citations SET doi=%s WHERE citation_id=%s", updates)
                conn.commit()
                updates.clear()
        if args.apply and updates:
            with conn.cursor() as cur:
                cur.executemany("UPDATE citations SET doi=%s WHERE citation_id=%s", updates)
            conn.commit()
    print(
        f"papers={len(papers)} scanned={scanned} missing_xml={missing} "
        f"misaligned={misaligned} failed={failed} would_update={changed} apply={args.apply}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
