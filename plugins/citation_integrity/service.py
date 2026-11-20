"""Deterministic citation metadata checks against Crossref and PubMed."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from typing import Any, Callable

CROSSREF = "https://api.crossref.org/works/"
PUBMED = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json&id="
USER_AGENT = "SciPal-CitationIntegrity/0.1 (mailto:local@scipal.invalid)"

Fetcher = Callable[[str], dict[str, Any]]

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = int(os.environ.get("SCIPAL_CITATION_CACHE_TTL", "3600"))
_CACHE_MAX = 1000


def _cache_get(key: str) -> dict[str, Any] | None:
    if _CACHE_TTL <= 0:
        return None
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if not item:
            return None
        if time.time() - item[0] > _CACHE_TTL:
            _CACHE.pop(key, None)
            return None
        return item[1]


def _cache_set(key: str, value: dict[str, Any]) -> None:
    if _CACHE_TTL <= 0:
        return
    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = (time.time(), value)


class NotFound(LookupError):
    pass


def normalize_doi(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", text, flags=re.IGNORECASE)
    return text.strip().lower()


def normalize_pmid(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^pmid:\s*", "", text, flags=re.IGNORECASE)
    return text if text.isdigit() else ""


def _text(value: Any) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return re.sub(r"\W+", " ", _text(value).casefold()).strip()


def _title_match(local: str, remote: str) -> bool:
    left, right = _norm(local), _norm(remote)
    if not left or not right:
        return True
    return SequenceMatcher(None, left, right).ratio() >= 0.90


def _year(value: Any) -> str:
    text = _text(value)
    match = re.search(r"(19|20)\d{2}", text)
    return match.group(0) if match else ""


def _family(value: Any) -> str:
    if isinstance(value, dict):
        if value.get("family") or value.get("last"):
            return _text(value.get("family") or value.get("last"))
        text = _text(value.get("name"))
        return text.split()[0] if text else ""
    text = _text(value)
    return text.split()[-1] if text else ""


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise NotFound(url) from exc
        raise LookupError(f"HTTP {exc.code}") from exc


def resolve_crossref(doi: str, fetcher: Fetcher = fetch_json) -> dict[str, Any]:
    cache_key = f"crossref:{doi}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return dict(cached)
    payload = fetcher(CROSSREF + urllib.parse.quote(doi, safe=""))
    message = payload.get("message") or {}
    if not message.get("DOI"):
        raise NotFound(doi)
    retracted = any(
        str(item.get("type") or "").lower() == "retraction"
        for item in (message.get("update-to") or [])
    )
    result = {
        "source": "crossref",
        "doi": normalize_doi(message.get("DOI")),
        "title": _text(message.get("title")),
        "authors": [
            {"family": _family(item), "given": _text(item.get("given"))}
            for item in (message.get("author") or [])
        ],
        "year": _year((((message.get("issued") or {}).get("date-parts") or [[""]])[0] or [""])[0]),
        "journal": _text(message.get("container-title")),
        "retracted": retracted,
        "retraction_status": "flagged" if retracted else "not_flagged",
        "retraction_source": "crossref-update-to",
    }
    _cache_set(cache_key, result)
    return dict(result)


def resolve_pubmed(pmid: str, fetcher: Fetcher = fetch_json) -> dict[str, Any]:
    cache_key = f"pubmed:{pmid}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return dict(cached)
    payload = fetcher(PUBMED + urllib.parse.quote(pmid, safe=""))
    result = (payload.get("result") or {}).get(pmid) or {}
    if not result or result.get("error"):
        raise NotFound(pmid)
    doi = ""
    for item in result.get("articleids") or []:
        if str(item.get("idtype") or "").lower() == "doi":
            doi = normalize_doi(item.get("value"))
            break
    result = {
        "source": "pubmed",
        "doi": doi,
        "pmid": pmid,
        "title": _text(result.get("title")),
        "authors": [{"family": _family(item), "given": ""} for item in (result.get("authors") or [])],
        "year": _year(result.get("pubdate")),
        "journal": _text(result.get("fulljournalname")),
        "retracted": None,
        "retraction_status": "unknown",
        "retraction_source": "pubmed",
    }
    _cache_set(cache_key, result)
    return dict(result)


def compare_reference(reference: dict[str, Any], remote: dict[str, Any]) -> list[dict[str, str]]:
    issues = []
    if reference.get("title") and remote.get("title") and not _title_match(reference["title"], remote["title"]):
        issues.append({"field": "title", "expected": _text(reference["title"]), "actual": remote["title"]})
    if reference.get("year") and remote.get("year") and _year(reference["year"]) != remote["year"]:
        issues.append({"field": "year", "expected": _year(reference["year"]), "actual": remote["year"]})
    local_first = _family((reference.get("authors") or [""])[0]) if reference.get("authors") else ""
    remote_first = _family((remote.get("authors") or [{}])[0]) if remote.get("authors") else ""
    if local_first and remote_first and local_first.casefold() != remote_first.casefold():
        issues.append({"field": "first_author", "expected": local_first, "actual": remote_first})
    if reference.get("journal") and remote.get("journal") and _norm(reference["journal"]) != _norm(remote["journal"]):
        issues.append({"field": "journal", "expected": _text(reference["journal"]), "actual": remote["journal"]})
    local_doi = normalize_doi(reference.get("doi"))
    if local_doi and remote.get("doi") and local_doi != remote["doi"]:
        issues.append({"field": "doi", "expected": local_doi, "actual": remote["doi"]})
    return issues


def check_reference(reference: dict[str, Any], fetcher: Fetcher = fetch_json) -> dict[str, Any]:
    doi = normalize_doi(reference.get("doi"))
    pmid = normalize_pmid(reference.get("pmid"))
    if not doi and not pmid:
        return {"status": "unverifiable", "issues": [], "reason": "doi or pmid is required", "resolved": None}
    remote = None
    errors = []
    if doi:
        try:
            remote = resolve_crossref(doi, fetcher)
        except NotFound:
            errors.append("crossref: not found")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"crossref: {exc}")
    if remote is None and pmid:
        try:
            remote = resolve_pubmed(pmid, fetcher)
        except NotFound:
            errors.append("pubmed: not found")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"pubmed: {exc}")
    if remote is None:
        status = "not_found" if errors and all("not found" in item for item in errors) else "error"
        return {"status": status, "issues": [], "reason": "; ".join(errors), "resolved": None}
    issues = compare_reference(reference, remote)
    if remote.get("retracted"):
        return {"status": "retracted", "issues": issues, "resolved": remote}
    return {
        "status": "mismatch" if issues else "verified",
        "issues": issues,
        "resolved": remote,
    }
