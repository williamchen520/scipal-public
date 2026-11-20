"""B3: OpenAlex/Crossref metadata and citation enrichment."""

from __future__ import annotations

import hashlib
import os
from typing import Any

import psycopg

from services.papers import citations, external_ids
from services.search import metadata_sources


class EnrichError(ValueError):
    pass


def _dsn() -> str:
    return (
        os.environ.get("SCIPAL_PAPER_DSN", "").strip()
        or os.environ.get("SCIPAL_PG_OWNER_DSN", "").strip()
        or os.environ.get("SCIPAL_PG_CORPUS_DSN", "").strip()
    )


def _edge_id(source: str, src: str, key: str) -> str:
    return "edge_" + hashlib.sha1(
        f"{source}:{src}:{key}".encode("utf-8")
    ).hexdigest()[:20]


def _doi(paper_id: str, dsn: str) -> str:
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            "SELECT doi FROM papers WHERE paper_id=%s", (paper_id,)
        ).fetchone()
    if not row:
        raise EnrichError("paper not found")
    doi = (row[0] or "").strip()
    if not doi:
        raise EnrichError("paper has no DOI")
    return doi


def enrich_paper(paper_id: str, *, dsn: str = "") -> dict[str, Any]:
    dsn = dsn or _dsn()
    doi = _doi(paper_id, dsn)
    external_ids.upsert_external_id(
        paper_id=paper_id, source="doi", external_id=doi, dsn=dsn
    )
    result: dict[str, Any] = {
        "paper_id": paper_id,
        "doi": doi,
        "external_ids": 1,
        "references": 0,
        "citations": 0,
        "resolved_local": 0,
        "sources": [],
        "errors": [],
    }

    work: dict[str, Any] = {}
    try:
        work = metadata_sources.openalex_work(doi)
        openalex_id = str(work.get("id") or "").rsplit("/", 1)[-1]
        if openalex_id:
            external_ids.upsert_external_id(
                paper_id=paper_id,
                source="openalex",
                external_id=openalex_id,
                metadata={"title": work.get("title"), "year": work.get("year")},
                dsn=dsn,
            )
            result["external_ids"] += 1
        result["sources"].append("openalex")
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"openalex work: {exc}"[:300])

    refs: list[dict[str, Any]] = []
    if work.get("referenced_works"):
        ids = [str(item).rsplit("/", 1)[-1] for item in work["referenced_works"]]
        resolved: dict[str, str] = {}
        try:
            resolved = metadata_sources.openalex_resolve_ids(ids)
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(f"openalex resolve: {exc}"[:300])
        for openalex_id in ids:
            refs.append(
                {
                    "source": "openalex",
                    "dst_external_source": "openalex",
                    "dst_external_id": openalex_id,
                    "dst_doi": resolved.get(openalex_id, ""),
                }
            )
    if not refs:
        try:
            crossref = metadata_sources.crossref_work(doi)
            refs = [
                {
                    "source": "crossref",
                    "dst_doi": ref.get("doi") or "",
                    "dst_title": ref.get("title") or "",
                }
                for ref in crossref.get("references") or []
            ]
            if refs:
                result["sources"].append("crossref")
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(f"crossref refs: {exc}"[:300])

    for index, ref in enumerate(refs):
        key = (
            ref.get("dst_doi")
            or f"{ref.get('dst_external_source')}:{ref.get('dst_external_id')}"
            or f"title:{ref.get('dst_title')}:{index}"
        )
        try:
            citations.upsert_edge(
                source=ref.get("source") or "openalex",
                src_paper_id=paper_id,
                dst_doi=ref.get("dst_doi") or "",
                dst_external_source=ref.get("dst_external_source") or "",
                dst_external_id=ref.get("dst_external_id") or "",
                dst_title=ref.get("dst_title") or "",
                edge_id=_edge_id("ref", paper_id, key),
                provenance={"enrich": ref.get("source") or "openalex", "doi": doi},
                dsn=dsn,
            )
            result["references"] += 1
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(f"reference edge: {exc}"[:300])

    try:
        for item in metadata_sources.openalex_cited_by(doi):
            external_id = str(item.get("id") or "")
            src_doi = item.get("doi") or ""
            key = external_id or src_doi or str(item.get("title") or "")
            src_paper = (
                external_ids.resolve_paper_by_external_id("doi", src_doi, dsn=dsn)
                if src_doi
                else None
            )
            citations.upsert_edge(
                source="openalex",
                src_paper_id=src_paper or "",
                src_doi=src_doi,
                src_external_source="openalex" if external_id else "",
                src_external_id=external_id,
                dst_paper_id=paper_id,
                dst_doi=doi,
                dst_title=item.get("title") or "",
                dst_year=str(item.get("year") or ""),
                edge_id=_edge_id("cite", paper_id, key),
                provenance={"enrich": "openalex_cited_by", "doi": doi},
                dsn=dsn,
            )
            result["citations"] += 1
        if result["citations"]:
            result["sources"].append("openalex_cited_by")
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"openalex cited_by: {exc}"[:300])

    try:
        resolved = citations.resolve_local_destinations(dsn=dsn)
        result["resolved_local"] = resolved.get("resolved", 0)
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"local resolve: {exc}"[:300])

    result["sources"] = sorted(set(result["sources"]))
    result["ok"] = not result["errors"]
    return result
