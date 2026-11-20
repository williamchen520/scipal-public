"""D4: create or upgrade abstract-only papers from online candidates."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import psycopg

from services.papers import external_ids, review


def _dsn() -> str:
    return (
        os.environ.get("SCIPAL_PG_OWNER_DSN", "").strip()
        or os.environ.get("SCIPAL_PG_CORPUS_DSN", "").strip()
    )


def abstract_paper_id(source: str, external_id: str) -> str:
    return "paper_online_" + hashlib.sha1(
        f"{source}:{external_id}".encode("utf-8")
    ).hexdigest()[:12]


def _existing_by_doi(conn, doi: str) -> tuple[str, str] | None:
    if not doi:
        return None
    row = conn.execute(
        "SELECT paper_id,acquisition FROM papers WHERE lower(doi)=lower(%s) "
        "ORDER BY (acquisition='fulltext') DESC,paper_id LIMIT 1",
        (doi,),
    ).fetchone()
    return (row[0], row[1] or "") if row else None


def ensure_abstract_paper(candidate: dict[str, Any], *, dsn: str = "") -> dict[str, Any]:
    dsn = dsn or _dsn()
    source = str(candidate.get("source") or "").strip()
    external_id = str(candidate.get("external_id") or "").strip()
    if not source or not external_id:
        raise ValueError("source and external_id are required")
    with psycopg.connect(dsn) as conn:
        existing = _existing_by_doi(conn, str(candidate.get("doi") or ""))
        if existing and existing[1] == "fulltext":
            return {"paper_id": existing[0], "already_fulltext": True}
        paper_id = existing[0] if existing else abstract_paper_id(source, external_id)
        conn.execute(
            "INSERT INTO papers "
            "(paper_id,title,doi,abstract,journal,year,authors,filename,"
            "parse_status,parse_engine,acquisition,total_paragraphs) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,'','metadata','online_metadata','abstract',0) "
            "ON CONFLICT (paper_id) DO UPDATE SET "
            "title=EXCLUDED.title,abstract=EXCLUDED.abstract,"
            "journal=EXCLUDED.journal,year=EXCLUDED.year,authors=EXCLUDED.authors,"
            "parse_engine=CASE WHEN papers.acquisition='fulltext' THEN papers.parse_engine "
            "ELSE 'online_metadata' END,"
            "acquisition=CASE WHEN papers.acquisition='fulltext' THEN 'fulltext' ELSE 'abstract' END",
            (
                paper_id,
                str(candidate.get("title") or "Untitled online paper"),
                str(candidate.get("doi") or ""),
                str(candidate.get("abstract") or ""),
                str(candidate.get("journal") or ""),
                str(candidate.get("year") or "")[:4] or None,
                json.dumps(candidate.get("authors") or [], ensure_ascii=False),
            ),
        )
        source_id = "src_online_" + hashlib.sha1(
            f"{paper_id}:{source}:{external_id}".encode()
        ).hexdigest()[:16]
        conn.execute(
            "INSERT INTO paper_sources "
            "(source_id,paper_id,source_kind,source_uri,parser,parser_version,is_primary,metadata) "
            "VALUES (%s,%s,'online_metadata',%s,'online','v1',true,%s::jsonb) "
            "ON CONFLICT (paper_id,source_kind,source_uri) DO NOTHING",
            (
                source_id,
                paper_id,
                str(candidate.get("url") or f"{source}:{external_id}"),
                json.dumps(candidate.get("provenance") or {}, ensure_ascii=False),
            ),
        )
        conn.commit()
    for source_name, value in (
        ("doi", candidate.get("doi") or ""),
        ("pmid", candidate.get("pmid") or ""),
        ("pmcid", candidate.get("pmcid") or ""),
        ("openalex", candidate.get("external_id") if source == "openalex" else ""),
        (source, external_id),
    ):
        if value:
            external_ids.upsert_external_id(
                paper_id=paper_id,
                source=source_name,
                external_id=str(value),
                metadata={"online_candidate": True},
                dsn=dsn,
            )
    review.ensure_review(paper_id, dsn)
    return {"paper_id": paper_id, "already_fulltext": False}
