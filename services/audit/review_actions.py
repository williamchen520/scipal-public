"""Append-only human review actions for evidence ledgers."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ACTIONS = {"accept", "add_evidence", "remove_claim", "flag_missing"}
_LOCK = threading.Lock()


def _pg_enabled() -> bool:
    return os.environ.get("SCIPAL_AUDIT_PG", "").strip().lower() in {"1", "true", "yes", "on"}


def actions_path() -> Path:
    return Path(os.environ.get("SCIPAL_LEDGER_ACTIONS_PATH", "logs/ledger-review-actions.jsonl"))


def record(
    *,
    answer_id: str,
    action: str,
    target_id: str = "",
    note: str = "",
    actor: str = "",
) -> dict[str, Any]:
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {sorted(ACTIONS)}")
    event = {
        "action_id": f"act_{uuid.uuid4().hex[:12]}",
        "answer_id": answer_id,
        "action": action,
        "target_id": target_id,
        "note": note[:500],
        "actor": actor,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if _pg_enabled():
        from services.audit.pg_store import record_action
        return {**event, "chain_event": record_action(event)}
    path = actions_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def list_actions(answer_id: str) -> list[dict[str, Any]]:
    if _pg_enabled():
        from services.audit.pg_store import list_actions as pg_list
        return pg_list(answer_id)
    path = actions_path()
    if not path.exists():
        return []
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [row for row in rows if row.get("answer_id") == answer_id]
