#!/usr/bin/env python3
"""Extract bracket-number citation contexts from the local corpus.

This is a SciNet-lite foundation, not a sentiment classifier: it records the
context and marks sentiment as unknown for later human/LLM labeling.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable

BRACKET = re.compile(r"\[([0-9][0-9,\-–\s]*)\]")
SENTENCE = re.compile(r"[^.!?]+[.!?]?")


def expand_refs(token: str) -> list[int]:
    refs: list[int] = []
    for part in token.replace("–", "-").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            left, _, right = part.partition("-")
            if left.isdigit() and right.isdigit():
                start, end = int(left), int(right)
                if 0 < end - start <= 50:
                    refs.extend(range(start, end + 1))
            continue
        if part.isdigit():
            refs.append(int(part))
    return sorted(set(refs))


def _cell(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    return str(value or "")


def extract_contexts(
    text: str,
    citations_by_ref: dict[int, dict[str, Any]],
    *,
    window: int = 220,
) -> list[dict[str, Any]]:
    rows = []
    for match in BRACKET.finditer(text or ""):
        for ref in expand_refs(match.group(1)):
            citation = citations_by_ref.get(ref)
            if not citation:
                continue
            start = max(0, match.start() - window)
            end = min(len(text), match.end() + window)
            context = re.sub(r"\s+", " ", text[start:end]).strip()
            sentence = ""
            for candidate in SENTENCE.finditer(text[start:end]):
                if candidate.start() <= match.start() - start <= candidate.end():
                    sentence = re.sub(r"\s+", " ", candidate.group(0)).strip()
                    break
            rows.append({
                "citation_id": citation.get("citation_id", ""),
                "citing_paper_id": citation.get("paper_id", ""),
                "ref_number": ref,
                "cited_doi": citation.get("doi", ""),
                "cited_title": citation.get("title", ""),
                "context": context,
                "sentence": sentence,
                "char_start": start,
                "char_end": end,
                "method": "bracket-number",
                "sentiment": "unknown",
            })
    return rows


def _paper_rows(conn, limit: int) -> Iterable[tuple[str, list[dict[str, Any]]]]:
    papers = conn.execute(
        "SELECT DISTINCT paper_id FROM citations "
        "WHERE paper_id IS NOT NULL AND btrim(paper_id) <> '' "
        "ORDER BY paper_id LIMIT %s",
        (limit,),
    ).fetchall()
    for (paper_id,) in papers:
        citations = conn.execute(
            "SELECT citation_id,paper_id,ref_number,doi,title FROM citations "
            "WHERE paper_id=%s ORDER BY ref_number",
            (paper_id,),
        ).fetchall()
        by_ref = {}
        for citation_id, citing, ref_number, doi, title in citations:
            digits = re.sub(r"\D", "", str(ref_number or ""))
            if digits:
                by_ref[int(digits)] = {
                    "citation_id": citation_id,
                    "paper_id": citing,
                    "doi": doi or "",
                    "title": title or "",
                }
        paragraphs = conn.execute(
            "SELECT text,section_level1,section_level2 FROM paragraphs "
            "WHERE paper_id=%s ORDER BY sequence",
            (paper_id,),
        ).fetchall()
        yield paper_id, [{
            "text": row[0] or "",
            "section": " / ".join(item for item in (row[1], row[2]) if item),
            "citations": by_ref,
        } for row in paragraphs]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default="")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--out", default="artifacts/scinet-lite-contexts.jsonl")
    args = parser.parse_args()
    dsn = args.dsn.strip()
    if not dsn:
        raise SystemExit("--dsn is required")
    import psycopg

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    count = papers = 0
    with psycopg.connect(dsn) as conn, out.open("w", encoding="utf-8") as handle:
        for paper_id, paragraphs in _paper_rows(conn, max(1, args.limit)):
            papers += 1
            for paragraph in paragraphs:
                for row in extract_contexts(paragraph["text"], paragraph["citations"]):
                    row["section"] = paragraph["section"]
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                    count += 1
    print(f"papers={papers} contexts={count} out={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
