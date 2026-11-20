"""Check that production retrieval stays on the accepted default path."""

from __future__ import annotations

import json
import os
from typing import Mapping


EXPERIMENTAL_FLAGS = {
    "SCIPAL_SENTENCE_EXPANSION": "query expansion (S2.1, rejected)",
    "SCIPAL_SECTION_ROUTING": "section routing (S2.2, below threshold)",
    "SCIPAL_PAPER_CANDIDATES": "paper FTS candidates (S2.3, rejected)",
    "SCIPAL_PAPER_VECTOR": "paper embeddings (S2.3b, rejected)",
    "SCIPAL_PAPER_QUOTA": "paper quota (S2.3d, rejected)",
}


def _enabled(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "on", "yes"}


def check_defaults(env: Mapping[str, str] | None = None) -> dict:
    env = os.environ if env is None else env
    backend = (env.get("SCIPAL_EVIDENCE_BACKEND") or "sentence").strip().lower()
    enabled = {
        name: reason
        for name, reason in EXPERIMENTAL_FLAGS.items()
        if _enabled(env.get(name, "0"))
    }
    return {
        "ok": backend == "sentence" and not enabled,
        "evidence_backend": backend,
        "experimental_enabled": enabled,
        "expected_backend": "sentence",
    }


def main() -> int:
    result = check_defaults()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
