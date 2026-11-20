"""Search event logging and bad-case feedback."""

from __future__ import annotations

import os
import uuid
from typing import Any

import psycopg

_SCHEMA_READY = False


def ensure_schema(dsn: str) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with psycopg.connect(dsn) as conn:
        exists = conn.execute(
            "SELECT to_regclass('code_rag.search_events'), to_regclass('code_rag.search_feedback')"
        ).fetchone()
        if all(exists):
            _SCHEMA_READY = True
            return
        conn.execute(
            "CREATE TABLE IF NOT EXISTS code_rag.search_events ("
            "event_id text PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now(), "
            "library_id text NOT NULL, query text NOT NULL, mode text NOT NULL DEFAULT '', "
            "backend text NOT NULL DEFAULT '', top_k integer NOT NULL DEFAULT 0, "
            "latency_ms double precision NOT NULL DEFAULT 0, hit_count integer NOT NULL DEFAULT 0, "
            "top_unit_id text NOT NULL DEFAULT '', top_path text NOT NULL DEFAULT '', "
            "workspace_id text NOT NULL DEFAULT '')"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS code_rag.search_feedback ("
            "feedback_id text PRIMARY KEY, event_id text NOT NULL REFERENCES code_rag.search_events(event_id), "
            "verdict text NOT NULL, expected_path text NOT NULL DEFAULT '', note text NOT NULL DEFAULT '', "
            "created_at timestamptz NOT NULL DEFAULT now())"
        )
        conn.commit()
    _SCHEMA_READY = True


def record_event(
    *,
    dsn: str,
    library_id: str,
    query: str,
    mode: str,
    backend: str,
    top_k: int,
    latency_ms: float,
    hits: list[dict[str, Any]],
    workspace_id: str = "",
) -> str:
    if not dsn:
        return ""
    try:
        ensure_schema(dsn)
        event_id = uuid.uuid4().hex
        top = hits[0] if hits else {}
        with psycopg.connect(dsn) as conn:
            conn.execute(
                "INSERT INTO code_rag.search_events (event_id,library_id,query,mode,backend,"
                "top_k,latency_ms,hit_count,top_unit_id,top_path,workspace_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    event_id,
                    library_id,
                    (query or "")[:2000],
                    mode,
                    backend,
                    top_k,
                    round(latency_ms, 3),
                    len(hits),
                    str(top.get("unit_id") or ""),
                    str(top.get("path") or ""),
                    workspace_id,
                ),
            )
            conn.commit()
        return event_id
    except Exception as exc:  # noqa: BLE001
        print(f"FEEDBACK_EVENT_ERROR {exc}", flush=True)
        return ""


def record_feedback(
    *,
    dsn: str,
    library_id: str,
    event_id: str,
    verdict: str,
    expected_path: str = "",
    note: str = "",
) -> tuple[bool, str]:
    if verdict not in {"wrong", "missing", "good"}:
        return False, "invalid verdict"
    try:
        with psycopg.connect(dsn) as conn:
            row = conn.execute(
                "SELECT library_id FROM code_rag.search_events WHERE event_id=%s",
                (event_id,),
            ).fetchone()
            if not row or row[0] != library_id:
                return False, "event not found"
            conn.execute(
                "INSERT INTO code_rag.search_feedback (feedback_id,event_id,verdict,expected_path,note) "
                "VALUES (%s,%s,%s,%s,%s)",
                (uuid.uuid4().hex, event_id, verdict, expected_path[:1000], note[:2000]),
            )
            conn.commit()
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
