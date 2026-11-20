"""Sandbox execution audit events (code_rag.execution_events)."""

from __future__ import annotations

import uuid
from typing import Any

import psycopg


def record_execution(
    *,
    dsn: str,
    library_id: str,
    proposal_id: str = "",
    status: str = "",
    exit_code: int | None = None,
    duration_seconds: float | None = None,
    test_module: str = "",
    image: str = "",
    workspace_id: str = "",
    error: str = "",
) -> str:
    execution_id = uuid.uuid4().hex
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "INSERT INTO code_rag.execution_events "
            "(execution_id,library_id,proposal_id,status,exit_code,duration_seconds,"
            "test_module,image,workspace_id,error) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                execution_id, library_id, proposal_id[:128], status[:32],
                exit_code, duration_seconds, test_module[:200], image[:300],
                workspace_id[:128], error[:1000],
            ),
        )
        conn.commit()
    return execution_id


def list_executions(*, dsn: str, library_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            "SELECT execution_id,created_at,library_id,proposal_id,status,exit_code,"
            "duration_seconds,test_module,image,workspace_id,error "
            "FROM code_rag.execution_events WHERE library_id=%s "
            "ORDER BY created_at DESC LIMIT %s",
            (library_id, max(1, min(limit, 200))),
        ).fetchall()
    keys = ("execution_id", "created_at", "library_id", "proposal_id", "status",
            "exit_code", "duration_seconds", "test_module", "image", "workspace_id", "error")
    return [dict(zip(keys, row)) for row in rows]


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(round((p / 100) * (len(ordered) - 1)))))]


def summarize_executions(rows: list[dict[str, Any]]) -> dict[str, Any]:
    durations = [float(row["duration_seconds"]) for row in rows if row.get("duration_seconds") is not None]
    passed = sum(1 for row in rows if row.get("status") == "passed")
    failed = sum(1 for row in rows if row.get("status") == "failed")
    timeouts = sum(1 for row in rows if row.get("status") == "timeout")
    return {
        "executions": len(rows),
        "passed": passed,
        "failed": failed,
        "timeouts": timeouts,
        "pass_rate": round(passed / len(rows), 4) if rows else None,
        "median_duration_seconds": round(sorted(durations)[len(durations) // 2], 3) if durations else None,
        "p95_duration_seconds": round(_percentile(durations, 95), 3) if durations else None,
        "total_duration_seconds": round(sum(durations), 3) if durations else 0.0,
    }


def execution_stats(*, dsn: str, library_id: str, days: int = 30) -> dict[str, Any]:
    days = max(1, min(days, 365))
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            "SELECT status,duration_seconds FROM code_rag.execution_events "
            "WHERE library_id=%s AND created_at >= now() - (%s * interval '1 day')",
            (library_id, days),
        ).fetchall()
    return {"library_id": library_id, "days": days, **summarize_executions(
        [{"status": row[0], "duration_seconds": row[1]} for row in rows]
    )}
