"""B1: external paper identifiers."""

from __future__ import annotations

import json
import os
from typing import Any

import psycopg


class ExternalIdError(ValueError):
    pass


def _dsn() -> str:
    return (
        os.environ.get("SCIPAL_PAPER_DSN", "").strip()
        or os.environ.get("SCIPAL_PG_OWNER_DSN", "").strip()
        or os.environ.get("SCIPAL_PG_CORPUS_DSN", "").strip()
    )


def _normalize(source: str, external_id: str) -> tuple[str, str]:
    source = str(source or "").strip().lower()
    external_id = str(external_id or "").strip()
    if not source:
        raise ExternalIdError("source is required")
    if not external_id:
        raise ExternalIdError("external_id is required")
    if source == "doi":
        external_id = external_id.lower().removeprefix("https://doi.org/")
    return source, external_id


def _row(row) -> dict[str, Any]:
    return {
        "paper_id": row[0],
        "source": row[1],
        "external_id": row[2],
        "confidence": float(row[3]),
        "metadata": row[4] or {},
        "fetched_at": row[5].isoformat() if row[5] else None,
    }


_COLUMNS = "paper_id,source,external_id,confidence,metadata,fetched_at"


def upsert_external_id(
    *,
    paper_id: str,
    source: str,
    external_id: str,
    confidence: float = 1.0,
    metadata: dict[str, Any] | None = None,
    dsn: str = "",
) -> dict[str, Any]:
    paper_id = str(paper_id or "").strip()
    if not paper_id:
        raise ExternalIdError("paper_id is required")
    source, external_id = _normalize(source, external_id)
    confidence = float(confidence)
    if not 0.0 <= confidence <= 1.0:
        raise ExternalIdError("confidence must be 0..1")
    dsn = dsn or _dsn()
    with psycopg.connect(dsn) as conn:
        if not conn.execute(
            "SELECT 1 FROM papers WHERE paper_id=%s", (paper_id,)
        ).fetchone():
            raise ExternalIdError("paper not found")
        row = conn.execute(
            "INSERT INTO paper_external_ids "
            "(paper_id,source,external_id,confidence,metadata,fetched_at) "
            "VALUES (%s,%s,%s,%s,%s::jsonb,now()) "
            "ON CONFLICT (paper_id,source,external_id) DO UPDATE SET "
            "confidence=EXCLUDED.confidence,metadata=EXCLUDED.metadata,fetched_at=now() "
            f"RETURNING {_COLUMNS}",
            (
                paper_id,
                source,
                external_id,
                confidence,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        ).fetchone()
        conn.commit()
    return _row(row)


def list_external_ids(
    paper_id: str, *, source: str = "", dsn: str = ""
) -> list[dict[str, Any]]:
    dsn = dsn or _dsn()
    where = "paper_id=%s"
    params: list[Any] = [paper_id]
    if source:
        where += " AND source=%s"
        params.append(str(source).strip().lower())
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM paper_external_ids WHERE {where} "
            "ORDER BY source,external_id",
            tuple(params),
        ).fetchall()
    return [_row(row) for row in rows]


def resolve_paper_by_external_id(
    source: str, external_id: str, *, dsn: str = ""
) -> str | None:
    source, external_id = _normalize(source, external_id)
    dsn = dsn or _dsn()
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            "SELECT paper_id FROM paper_external_ids "
            "WHERE source=%s AND external_id=%s "
            "ORDER BY confidence DESC,fetched_at DESC LIMIT 1",
            (source, external_id),
        ).fetchone()
    return row[0] if row else None
