"""D3: online candidate auto-ingest worker."""

from __future__ import annotations

import hashlib
import ipaddress
import os
import socket
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import psycopg
import requests

from services.db.pg_pool import core_connection
from services.imports.orchestrator import process_import
from services.imports.paper_lane import PaperLaneAdapter
from services.imports.session import create_import
from services.online import abstract_paper, candidates, formats

MAX_BYTES = 50 * 1024 * 1024
SUFFIX = {"jats": ".xml", "html": ".html", "md": ".md", "pdf": ".pdf"}
CONTENT_TYPE = {
    "application/pdf": "pdf",
    "text/html": "html",
    "application/xhtml+xml": "html",
    "text/markdown": "md",
    "text/x-markdown": "md",
    "application/xml": "jats",
    "text/xml": "jats",
}


class IngestError(RuntimeError):
    pass


def _staging_root() -> Path:
    raw = os.environ.get("SCIPAL_ONLINE_STAGING_ROOT", "").strip()
    return Path(raw) if raw else Path("data/online/staging").resolve()


def _allowed_networks():
    raw = os.environ.get("SCIPAL_ONLINE_ALLOW_CIDRS", "").strip()
    return [ipaddress.ip_network(part.strip()) for part in raw.split(",") if part.strip()]


def _safe_url(url: str) -> str:
    parsed = urlparse(url or "")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise IngestError("only public http(s) URLs are allowed")
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except OSError as exc:
        raise IngestError(f"cannot resolve host: {exc}") from exc
    allowed = _allowed_networks()
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if any(ip in network for network in allowed):
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise IngestError("private/loopback URL is not allowed")
    return url


def _fetch(url: str) -> tuple[bytes, str]:
    current = url
    for _ in range(5):
        _safe_url(current)
        response = requests.get(
            current,
            timeout=30,
            stream=True,
            headers={"User-Agent": "SciPal/1.0 (open-access ingest)"},
            allow_redirects=False,
        )
        try:
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location", "")
                if not location:
                    raise IngestError("redirect without Location")
                current = urljoin(current, location)
                continue
            if response.status_code in {401, 402, 403}:
                raise IngestError(f"access denied: {response.status_code}")
            response.raise_for_status()
            ctype = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(1024 * 256):
                total += len(chunk)
                if total > MAX_BYTES:
                    raise IngestError("file too large")
                chunks.append(chunk)
            return b"".join(chunks), ctype
        finally:
            response.close()
    raise IngestError("too many redirects")


def _format(candidate: dict[str, Any], content_type: str) -> str | None:
    return formats.choose_format(
        best_format=str(candidate.get("best_format") or ""),
        url=str(candidate.get("url") or ""),
        content_type=content_type,
    ) or CONTENT_TYPE.get(content_type)


def _local_acquisition(paper_id: str) -> str:
    from services.imports.paper_build import _dsn

    with psycopg.connect(_dsn()) as conn:
        row = conn.execute(
            "SELECT acquisition FROM papers WHERE paper_id=%s", (paper_id,)
        ).fetchone()
    return (row[0] or "") if row else ""


def _local_by_doi(doi: str) -> str:
    if not doi:
        return ""
    from services.imports.paper_build import _dsn

    with psycopg.connect(_dsn()) as conn:
        row = conn.execute(
            "SELECT paper_id FROM papers WHERE lower(doi)=lower(%s) "
            "ORDER BY (acquisition='fulltext') DESC,paper_id LIMIT 1",
            (doi,),
        ).fetchone()
    return row[0] if row else ""


def _abstract(candidate: dict[str, Any]) -> dict[str, Any]:
    result = abstract_paper.ensure_abstract_paper(candidate)
    return candidates.mark_status(
        candidate["candidate_id"], "draft", local_paper_id=result["paper_id"]
    )


def claim_next() -> dict[str, Any] | None:
    with core_connection() as pg:
        row = pg.execute(
            "WITH next AS ("
            " SELECT candidate_id FROM online_candidates "
            " WHERE ingest_status='queued' ORDER BY fetched_at LIMIT 1 FOR UPDATE SKIP LOCKED"
            ") UPDATE online_candidates c SET ingest_status='fetching', updated_at=now() "
            "FROM next WHERE c.candidate_id=next.candidate_id "
            "RETURNING c.candidate_id,c.run_id,c.source,c.external_id,c.doi,c.pmid,c.pmcid,"
            "c.title,c.abstract,c.url,c.oa_status,c.has_fulltext,c.best_format,c.local_paper_id"
        ).fetchone()
        pg.commit()
    return dict(row) if row else None


def ingest(candidate: dict[str, Any]) -> dict[str, Any]:
    candidate_id = candidate["candidate_id"]
    override = str(candidate.get("local_paper_id") or "").strip()
    if not override:
        override = _local_by_doi(str(candidate.get("doi") or ""))
    acquisition = _local_acquisition(override) if override else ""
    if acquisition == "fulltext":
        return candidates.mark_status(candidate_id, "skipped", local_paper_id=override)
    url = str(candidate.get("url") or "").strip()
    if not url:
        return _abstract(candidate)
    try:
        data, ctype = _fetch(url)
        kind = _format(candidate, ctype)
        if kind is None:
            return _abstract(candidate)
        suffix = SUFFIX[kind]
        root = _staging_root() / candidate_id
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"source{suffix}"
        path.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        created = create_import(
            tenant_id="default",
            library_id="lib_default",
            origin="online",
            items=[
                {
                    "uri": url,
                    "staged_path": str(path),
                    "content_hash": digest,
                    "paper_id_override": override,
                }
            ],
        )
        result = process_import(
            created["import_id"], paper_adapter=PaperLaneAdapter(build=True)
        )
        item = (result.get("items") or [{}])[0]
        paper_id = (item.get("parsed_json") or {}).get("paper_id")
        if item.get("status") != "built" or not paper_id:
            return candidates.mark_status(
                candidate_id, "failed", error=str(item.get("error") or "build failed")
            )
        return candidates.mark_status(candidate_id, "draft", local_paper_id=paper_id)
    except IngestError:
        return _abstract(candidate)
    except Exception as exc:  # noqa: BLE001
        return candidates.mark_status(candidate_id, "failed", error=str(exc)[:500])


def run_once() -> dict[str, Any] | None:
    candidate = claim_next()
    if not candidate:
        return None
    return ingest(candidate)
