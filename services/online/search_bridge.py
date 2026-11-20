"""D5: enqueue top online hits as auto-ingest candidates."""

from __future__ import annotations

import hashlib
import os
from typing import Any

from services.online import candidates


def _top_n() -> int:
    try:
        return max(1, min(int(os.environ.get("SCIPAL_ONLINE_INGEST_TOP_N", "3")), 10))
    except ValueError:
        return 3


def _daily_budget() -> int:
    raw = os.environ.get("SCIPAL_ONLINE_DAILY_INGEST_BUDGET", "20").strip()
    try:
        value = int(raw)
    except ValueError:
        return 20
    return max(0, value)


def _source(row: dict[str, Any]) -> str:
    raw = str(row.get("source") or "")
    if "pmc" in raw:
        return "pmc"
    if "pubmed" in raw:
        return "pubmed"
    return raw.replace("online_", "") or "online"


def enqueue_online_results(
    items: list[dict[str, Any]], *, query: str, top_n: int | None = None
) -> dict[str, Any]:
    limit = top_n or _top_n()
    selected = [
        row for row in items if not row.get("in_local_db")
    ][:limit]
    if not selected:
        return {"run_id": "", "candidates": []}
    budget = _daily_budget()
    remaining = None if budget == 0 else max(0, budget - candidates.count_created_today())
    if remaining is not None:
        selected = selected[:remaining]
        if not selected:
            return {
                "run_id": "",
                "candidates": [],
                "skipped": "daily_budget",
                "budget": budget,
            }
    query_hash = hashlib.sha256((query or "").encode("utf-8")).hexdigest()
    run_id = candidates.create_run(
        query_hash=query_hash,
        source="mixed",
        counts={"found": len(items), "enqueued": len(selected)},
    )
    out = []
    for row in selected:
        source = _source(row)
        pmcid = str(row.get("pmcid") or "")
        pmid = str(row.get("pmid") or "")
        external = pmcid or pmid or str(row.get("paper_id") or "")
        if not external:
            continue
        url = (
            f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
            if pmcid
            else ""
        )
        created = candidates.upsert_candidate(
            run_id=run_id,
            source=source,
            external_id=external,
            title=str(row.get("title") or ""),
            abstract=str(row.get("abstract") or ""),
            doi=str(row.get("doi") or ""),
            pmid=pmid,
            pmcid=pmcid,
            authors=[],
            year=str(row.get("year") or ""),
            journal=str(row.get("journal") or ""),
            url=url,
            oa_status="oa" if pmcid else "unknown",
            has_fulltext=bool(pmcid),
            best_format="html" if pmcid else "",
            provenance={"query_hash": query_hash, "source": source},
        )
        out.append(
            {
                **created,
                "source": source,
                "external_id": external,
                "doi": str(row.get("doi") or ""),
                "title": str(row.get("title") or ""),
            }
        )
    return {"run_id": run_id, "candidates": out, "budget": budget, "remaining": remaining}
