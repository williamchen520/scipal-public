"""Local append-only evidence ledger store."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()


def _pg_enabled() -> bool:
    return os.environ.get("SCIPAL_AUDIT_PG", "").strip().lower() in {"1", "true", "yes", "on"}


def ledger_path() -> Path:
    return Path(os.environ.get("SCIPAL_LEDGER_PATH", "logs/evidence-ledgers.jsonl"))


def save(ledger: dict[str, Any]) -> None:
    if _pg_enabled():
        from services.audit.pg_store import save_ledger
        save_ledger(ledger)
        return
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(ledger, ensure_ascii=False) + "\n")


def list_ledgers(limit: int = 50) -> list[dict[str, Any]]:
    if _pg_enabled():
        from services.audit.pg_store import list_ledgers as pg_list
        return pg_list(limit)
    path = ledger_path()
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    items = [
        {
            "answer_id": row.get("answer_id"),
            "created_at": row.get("created_at"),
            "query": row.get("query"),
            "config_id": row.get("config_id"),
            "corpus_snapshot_id": row.get("corpus_snapshot_id"),
            "summary": row.get("summary") or {},
        }
        for row in rows
    ]
    return items[-max(1, min(limit, 1000)):][::-1]


def get_ledger(answer_id: str) -> dict[str, Any] | None:
    if _pg_enabled():
        from services.audit.pg_store import get_ledger as pg_get
        return pg_get(answer_id)
    path = ledger_path()
    if not path.exists():
        return None
    found = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("answer_id") == answer_id:
            found = row
    return found
