"""Aggregate audit-ledger, error and review-action metrics."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from services.audit.error_lifecycle import path as errors_path
from services.audit.ledger_store import ledger_path
from services.audit.review_actions import actions_path


def _pg_enabled() -> bool:
    import os
    return os.environ.get("SCIPAL_AUDIT_PG", "").strip().lower() in {"1", "true", "yes", "on"}


def _pg_metrics() -> dict[str, Any]:
    from services.db.pg_pool import core_connection
    with core_connection() as conn:
        ledgers = [row["payload"] for row in conn.execute("SELECT payload FROM audit_ledger").fetchall()]
        actions = [row["payload"] for row in conn.execute("SELECT payload FROM audit_event WHERE event_type=%s", ("action",)).fetchall()]
        error_rows = conn.execute("SELECT status, count(*) AS n FROM audit_error GROUP BY status").fetchall()
    claims = sum(len(row.get("claims") or []) for row in ledgers)
    evidence = sum(len(row.get("evidence") or []) for row in ledgers)
    cited = sum(1 for row in ledgers for ref in (row.get("evidence") or []) if ref.get("cited"))
    high = sum(1 for row in ledgers for ref in (row.get("evidence") or []) if ref.get("review_priority") == "high")
    uncited_claims = sum(1 for row in ledgers for claim in (row.get("claims") or []) if claim.get("support_status") == "uncited")
    statuses = {row["status"]: row["n"] for row in error_rows}
    closed = statuses.get("closed", 0)
    unresolved = statuses.get("unresolved", 0)
    action_counts: dict[str, int] = {}
    for row in actions:
        action = row.get("action") if isinstance(row, dict) else None
        if isinstance(action, dict):
            action = action.get("action")
        action = str(action or "unknown")
        action_counts[action] = action_counts.get(action, 0) + 1
    return {
        "ledgers": len(ledgers), "claims": claims, "evidence": evidence,
        "cited_evidence": cited, "high_priority": high, "uncited_claims": uncited_claims,
        "actions": len(actions), "actions_by_type": action_counts,
        "errors": sum(statuses.values()), "errors_by_status": statuses,
        "audit_yield_per_100_ledgers": round(100 * sum(statuses.values()) / len(ledgers), 2) if ledgers else 0.0,
        "review_burden_actions_per_ledger": round(len(actions) / len(ledgers), 2) if ledgers else 0.0,
        "closure_rate": round(closed / (closed + unresolved), 4) if (closed + unresolved) else None,
        "high_priority_rate": round(high / evidence, 4) if evidence else None,
        "uncited_claim_rate": round(uncited_claims / claims, 4) if claims else None,
    }


def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def metrics() -> dict[str, Any]:
    if _pg_enabled():
        return _pg_metrics()
    ledgers = _rows(ledger_path())
    errors = _rows(errors_path())
    actions = _rows(actions_path())
    latest_errors: dict[str, dict[str, Any]] = {}
    for row in errors:
        latest_errors[row["error_id"]] = row
    statuses = Counter(row.get("status", "") for row in latest_errors.values())
    action_counts = Counter(row.get("action", "") for row in actions)
    claims = sum(len(row.get("claims") or []) for row in ledgers)
    evidence = sum(len(row.get("evidence") or []) for row in ledgers)
    cited = sum(1 for row in ledgers for ref in (row.get("evidence") or []) if ref.get("cited"))
    high = sum(1 for row in ledgers for ref in (row.get("evidence") or []) if ref.get("review_priority") == "high")
    uncited_claims = sum(
        1 for row in ledgers for claim in (row.get("claims") or [])
        if claim.get("support_status") == "uncited"
    )
    closed = statuses.get("closed", 0)
    unresolved = statuses.get("unresolved", 0)
    return {
        "ledgers": len(ledgers),
        "claims": claims,
        "evidence": evidence,
        "cited_evidence": cited,
        "high_priority": high,
        "uncited_claims": uncited_claims,
        "actions": len(actions),
        "actions_by_type": dict(action_counts),
        "errors": len(latest_errors),
        "errors_by_status": dict(statuses),
        "audit_yield_per_100_ledgers": round(100 * len(latest_errors) / len(ledgers), 2) if ledgers else 0.0,
        "review_burden_actions_per_ledger": round(len(actions) / len(ledgers), 2) if ledgers else 0.0,
        "closure_rate": round(closed / (closed + unresolved), 4) if (closed + unresolved) else None,
        "high_priority_rate": round(high / evidence, 4) if evidence else None,
        "uncited_claim_rate": round(uncited_claims / claims, 4) if claims else None,
    }
