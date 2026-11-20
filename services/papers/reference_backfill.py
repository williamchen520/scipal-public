"""C1: backfill metadata for frequently referenced papers."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import psycopg

from services.papers import citations, external_ids
from services.search import metadata_sources


class BackfillError(ValueError):
    pass


def _dsn() -> str:
    return (
        os.environ.get("SCIPAL_PAPER_DSN", "").strip()
        or os.environ.get("SCIPAL_PG_OWNER_DSN", "").strip()
        or os.environ.get("SCIPAL_PG_CORPUS_DSN", "").strip()
    )


def top_referenced(*, limit: int = 20, dsn: str = "") -> list[str]:
    dsn = dsn or _dsn()
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            "SELECT dst_external_id,count(*) AS n FROM paper_citation_edges "
            "WHERE dst_paper_id IS NULL AND dst_external_source='openalex' "
            "AND dst_external_id IS NOT NULL "
            "GROUP BY dst_external_id ORDER BY n DESC,dst_external_id LIMIT %s",
            (max(1, min(int(limit), 50)),),
        ).fetchall()
    return [row[0] for row in rows]


def _paper_id(openalex_id: str) -> str:
    return "paper_ref_" + hashlib.sha1(openalex_id.encode("utf-8")).hexdigest()[:12]


def backfill(
    *, limit: int = 20, dry_run: bool = False, dsn: str = ""
) -> dict[str, Any]:
    dsn = dsn or _dsn()
    ids = top_referenced(limit=limit, dsn=dsn)
    works = metadata_sources.openalex_works_by_ids(ids)
    works.sort(key=lambda item: int(item.get("cited_by_count") or 0), reverse=True)
    selected = works[: max(1, min(int(limit), 50))]
    if dry_run:
        return {
            "dry_run": True,
            "candidates": [
                {
                    "openalex_id": item["openalex_id"],
                    "title": item["title"],
                    "doi": item["doi"],
                    "cited_by_count": item["cited_by_count"],
                }
                for item in selected
            ],
        }

    created = 0
    skipped = 0
    for item in selected:
        openalex_id = item["openalex_id"]
        paper_id = _paper_id(openalex_id)
        existing = external_ids.resolve_paper_by_external_id(
            "openalex", openalex_id, dsn=dsn
        )
        if existing:
            skipped += 1
            continue
        with psycopg.connect(dsn) as conn:
            conn.execute(
                "INSERT INTO papers "
                "(paper_id,title,doi,abstract,journal,year,authors,filename,"
                "parse_status,parse_engine,acquisition,total_paragraphs) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,'','metadata','openalex','reference',0) "
                "ON CONFLICT (paper_id) DO NOTHING",
                (
                    paper_id,
                    item.get("title") or "",
                    item.get("doi") or "",
                    item.get("abstract") or "",
                    item.get("journal") or "",
                    str(item.get("year") or "")[:4] or None,
                    json.dumps(
                        [author for author in item.get("authors") or [] if author],
                        ensure_ascii=False,
                    ),
                ),
            )
            conn.commit()
        external_ids.upsert_external_id(
            paper_id=paper_id,
            source="openalex",
            external_id=openalex_id,
            metadata={
                "title": item.get("title"),
                "year": item.get("year"),
                "cited_by_count": item.get("cited_by_count"),
            },
            dsn=dsn,
        )
        if item.get("doi"):
            external_ids.upsert_external_id(
                paper_id=paper_id, source="doi", external_id=item["doi"], dsn=dsn
            )
        created += 1

    resolved = citations.resolve_local_destinations(dsn=dsn)
    return {
        "dry_run": False,
        "selected": len(selected),
        "created": created,
        "skipped": skipped,
        "resolved": resolved.get("resolved", 0),
        "projected": resolved.get("projected", 0),
    }
