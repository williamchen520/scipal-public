"""Transactional outbox for audit regeneration jobs (PostgreSQL)."""

from __future__ import annotations

import json
from typing import Any

from services.db.pg_pool import core_connection


def enqueue(
    *,
    answer_id: str,
    error_id: str,
    action: str,
    payload: dict[str, Any],
    idempotency_key: str,
) -> dict[str, Any]:
    with core_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO audit_outbox(answer_id,error_id,action,payload,idempotency_key)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id, status
            """,
            (answer_id, error_id, action, json.dumps(payload, ensure_ascii=False), idempotency_key),
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT id, status FROM audit_outbox WHERE idempotency_key=%s",
                (idempotency_key,),
            ).fetchone()
    return {"id": row["id"], "status": row["status"]}


def claim(
    limit: int = 1,
    *,
    max_attempts: int = 3,
    stale_seconds: int = 300,
) -> list[dict[str, Any]]:
    with core_connection() as conn:
        conn.execute(
            """
            UPDATE audit_outbox
            SET status='unresolved', last_error='max attempts reached', updated_at=now()
            WHERE status='running' AND attempts >= %s
            """,
            (max_attempts,),
        )
        conn.execute(
            """
            UPDATE audit_outbox
            SET status='pending', last_error='stale requeue', updated_at=now()
            WHERE status='running'
              AND attempts < %s
              AND updated_at < now() - make_interval(secs => %s)
            """,
            (max_attempts, stale_seconds),
        )
        rows = conn.execute(
            """
            SELECT id, answer_id, error_id, action, attempts, payload
            FROM audit_outbox
            WHERE status='pending' AND attempts < %s
            ORDER BY id
            FOR UPDATE SKIP LOCKED
            LIMIT %s
            """,
            (max_attempts, max(1, min(limit, 100))),
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE audit_outbox SET status='running', attempts=attempts+1, updated_at=now() WHERE id=%s",
                (row["id"],),
            )
    return [dict(row) for row in rows]


def complete(job_id: int, *, status: str, last_error: str = "") -> None:
    if status not in {"done", "failed", "unresolved", "pending"}:
        raise ValueError("invalid outbox status")
    with core_connection() as conn:
        conn.execute(
            "UPDATE audit_outbox SET status=%s, last_error=%s, updated_at=now() WHERE id=%s",
            (status, last_error[:1000], job_id),
        )


def list_jobs(limit: int = 100) -> list[dict[str, Any]]:
    with core_connection() as conn:
        rows = conn.execute(
            "SELECT id, answer_id, error_id, action, status, attempts, last_error, created_at FROM audit_outbox ORDER BY id DESC LIMIT %s",
            (max(1, min(limit, 1000)),),
        ).fetchall()
    return [
        {**dict(row), "created_at": row["created_at"].isoformat() if row.get("created_at") else ""}
        for row in rows
    ]


def fail(job_id: int, *, last_error: str, max_attempts: int = 3) -> str:
    with core_connection() as conn:
        row = conn.execute("SELECT attempts FROM audit_outbox WHERE id=%s", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        status = "unresolved" if row["attempts"] >= max_attempts else "pending"
        conn.execute(
            "UPDATE audit_outbox SET status=%s, last_error=%s, updated_at=now() WHERE id=%s",
            (status, last_error[:1000], job_id),
        )
    return status
