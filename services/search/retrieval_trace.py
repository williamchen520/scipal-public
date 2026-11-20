"""Behavior-neutral retrieval trace writer (JSONL).

Enable with SCIPAL_RETRIEVAL_TRACE=1. This does not change ranking; it only
records the config and candidate pool needed for offline replay.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()


def enabled() -> bool:
    return os.environ.get("SCIPAL_RETRIEVAL_TRACE", "").strip().lower() in {"1", "true", "yes", "on"}


def config_id(config: dict[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def trace_path() -> Path:
    return Path(os.environ.get("SCIPAL_RETRIEVAL_TRACE_PATH", "logs/retrieval-traces.jsonl"))


def record(
    *,
    query: str,
    config: dict[str, Any],
    pool: list[dict[str, Any]],
    final: list[dict[str, Any]],
    latency_ms: float,
    trace_id: str | None = None,
) -> dict[str, Any]:
    record = {
        "trace_id": trace_id or f"rt_{uuid.uuid4().hex[:16]}",
        "timestamp_unix": time.time(),
        "query": query,
        "config_id": config_id(config),
        "config": config,
        "pool": pool,
        "final": final,
        "latency_ms": round(float(latency_ms), 3),
    }
    path = trace_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    with _LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
    return record
