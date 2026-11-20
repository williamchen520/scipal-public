"""Read-only Zoekt client for regex/symbol queries (library-scoped)."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any


def _base_url() -> str:
    value = os.environ.get("SCIPAL_ZOekt_URL", "").strip().rstrip("/")
    if not value:
        raise RuntimeError("SCIPAL_ZOekt_URL is required")
    return value


def _repo_map() -> dict[str, str]:
    raw = os.environ.get("SCIPAL_ZOekt_REPO_MAP", "{}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return {str(key): str(value) for key, value in data.items()} if isinstance(data, dict) else {}


def search_zoekt(
    query: str,
    *,
    library_id: str,
    top_k: int = 10,
    snapshot_id: str = "",
    mode: str = "regex",
    language: str = "",
    path_filter: str = "",
) -> list[dict[str, Any]]:
    repo = _repo_map().get(library_id, "")
    if not repo:
        return []
    clauses = [f"repo:{repo}"]
    if language:
        clauses.append(f"lang:{language}")
    if path_filter:
        clauses.append(f"file:{path_filter}")
    clauses.append(query)
    q = " ".join(clauses)
    url = _base_url() + "/search?" + urllib.parse.urlencode({"q": q, "format": "json"})
    with urllib.request.urlopen(url, timeout=20) as response:
        payload = json.loads(response.read())
    matches = payload.get("result", {}).get("FileMatches", [])
    results = []
    for rank, item in enumerate(matches[: max(1, min(int(top_k), 100))], 1):
        fragments = item.get("Matches", [{}])[0].get("Fragments", [{}])[0]
        snippet = (
            str(fragments.get("Pre", ""))
            + str(fragments.get("Match", ""))
            + str(fragments.get("Post", ""))
        ).strip()
        line = item.get("Matches", [{}])[0].get("LineNum", 0) or 0
        path = item.get("FileName", "")
        results.append(
            {
                "unit_id": f"zoekt:{repo}:{path}:{line}",
                "library_id": library_id,
                "snapshot_id": "",
                "symbol_name": path.rsplit("/", 1)[-1],
                "unit_type": "match",
                "snippet": snippet[:500],
                "start_line": line,
                "end_line": line,
                "path": f"{repo}/{path}",
                "score": round(1.0 / (60 + rank), 6),
            }
        )
    return results
