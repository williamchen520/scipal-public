"""D1: online search runs and candidate persistence."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from services.db.pg_pool import core_connection


class CandidateError(ValueError):
    pass


def candidate_id(source: str, external_id: str) -> str:
    source = str(source or "").strip().lower()
    external_id = str(external_id or "").strip()
    if not source or not external_id:
        raise CandidateError("source and external_id are required")
    return "cand_" + hashlib.sha1(f"{source}:{external_id}".encode()).hexdigest()[:16]


def create_run(
    *,
    query_hash: str,
    source: str,
    counts: dict[str, Any] | None = None,
    ttl_hours: int = 24,
) -> str:
    if not query_hash or not source:
        raise CandidateError("query_hash and source are required")
    run_id = "orun_" + uuid.uuid4().hex[:16]
    with core_connection() as pg:
        pg.execute(
            "INSERT INTO online_search_runs "
            "(run_id,query_hash,source,status,counts_json,expires_at) "
            "VALUES (%s,%s,%s,'completed',%s::jsonb,now() + (%s * interval '1 hour'))",
            (
                run_id,
                query_hash,
                source,
                json.dumps(counts or {}, ensure_ascii=False),
                max(1, int(ttl_hours)),
            ),
        )
        pg.commit()
    return run_id


def upsert_candidate(
    *,
    run_id: str,
    source: str,
    external_id: str,
    title: str,
    abstract: str = "",
    doi: str = "",
    pmid: str = "",
    pmcid: str = "",
    authors: list[str] | None = None,
    year: str = "",
    journal: str = "",
    url: str = "",
    oa_status: str = "",
    has_fulltext: bool = False,
    best_format: str = "",
    provenance: dict[str, Any] | None = None,
    ttl_hours: int = 24,
) -> dict[str, Any]:
    cid = candidate_id(source, external_id)
    with core_connection() as pg:
        row = pg.execute(
            "INSERT INTO online_candidates "
            "(candidate_id,run_id,source,external_id,doi,pmid,pmcid,title,abstract,authors,"
            "year,journal,url,oa_status,has_fulltext,best_format,provenance,expires_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s::jsonb,"
            "now() + (%s * interval '1 hour')) "
            "ON CONFLICT (candidate_id) DO UPDATE SET "
            "run_id=EXCLUDED.run_id,doi=EXCLUDED.doi,pmid=EXCLUDED.pmid,pmcid=EXCLUDED.pmcid,"
            "title=EXCLUDED.title,abstract=EXCLUDED.abstract,authors=EXCLUDED.authors,"
            "year=EXCLUDED.year,journal=EXCLUDED.journal,url=EXCLUDED.url,"
            "oa_status=EXCLUDED.oa_status,has_fulltext=EXCLUDED.has_fulltext,"
            "best_format=EXCLUDED.best_format,provenance=EXCLUDED.provenance,"
            "fetched_at=now(),expires_at=EXCLUDED.expires_at,updated_at=now() "
            "RETURNING candidate_id,ingest_status,local_paper_id",
            (
                cid,
                run_id,
                source,
                external_id,
                doi or None,
                pmid or None,
                pmcid or None,
                title or "",
                abstract or "",
                json.dumps(authors or [], ensure_ascii=False),
                str(year or "")[:4] or None,
                journal or None,
                url or None,
                oa_status or None,
                bool(has_fulltext),
                best_format or None,
                json.dumps(provenance or {}, ensure_ascii=False),
                max(1, int(ttl_hours)),
            ),
        ).fetchone()
        pg.commit()
    return {
        "candidate_id": row["candidate_id"],
        "ingest_status": row["ingest_status"],
        "local_paper_id": row["local_paper_id"] or "",
    }


def count_created_today() -> int:
    with core_connection() as pg:
        row = pg.execute(
            "SELECT count(*) AS n FROM online_candidates "
            "WHERE created_at >= date_trunc('day', now())"
        ).fetchone()
    return int(row["n"] or 0)


def list_candidates(
    *, run_id: str = "", status: str = "", limit: int = 100
) -> list[dict[str, Any]]:
    where = ["1=1"]
    params: list[Any] = []
    if run_id:
        where.append("run_id=%s")
        params.append(run_id)
    if status:
        where.append("ingest_status=%s")
        params.append(status)
    params.append(max(1, min(int(limit), 500)))
    with core_connection() as pg:
        rows = pg.execute(
            "SELECT candidate_id,run_id,source,external_id,doi,pmid,pmcid,title,"
            "abstract,url,oa_status,has_fulltext,best_format,local_paper_id,"
            "ingest_status,ingest_error,fetched_at,expires_at "
            f"FROM online_candidates WHERE {' AND '.join(where)} "
            "ORDER BY fetched_at DESC LIMIT %s",
            tuple(params),
        ).fetchall()
    return [dict(row) for row in rows]


def mark_status(
    candidate_id_value: str,
    status: str,
    *,
    error: str = "",
    local_paper_id: str = "",
) -> dict[str, Any]:
    if status not in {"queued", "fetching", "staged", "parsed", "draft", "failed", "skipped"}:
        raise CandidateError("invalid ingest status")
    with core_connection() as pg:
        row = pg.execute(
            "UPDATE online_candidates SET ingest_status=%s,ingest_error=%s,"
            "local_paper_id=COALESCE(NULLIF(%s,''),local_paper_id),updated_at=now() "
            "WHERE candidate_id=%s RETURNING candidate_id,ingest_status,local_paper_id",
            (status, error[:500], local_paper_id, candidate_id_value),
        ).fetchone()
        pg.commit()
    if not row:
        raise CandidateError("candidate not found")
    return {
        "candidate_id": row["candidate_id"],
        "ingest_status": row["ingest_status"],
        "local_paper_id": row["local_paper_id"] or "",
    }
