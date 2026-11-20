"""D2: choose the best available online full-text format."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

PRIORITY = ("jats", "html", "md", "pdf")
ALIASES = {
    "xml": "jats",
    "application/xml": "jats",
    "text/xml": "jats",
    "text/html": "html",
    "application/xhtml+xml": "html",
    "markdown": "md",
    "text/markdown": "md",
    "text/x-markdown": "md",
    "application/pdf": "pdf",
}
SUFFIX = {
    ".xml": "jats",
    ".html": "html",
    ".htm": "html",
    ".xhtml": "html",
    ".md": "md",
    ".markdown": "md",
    ".pdf": "pdf",
}


class FormatError(ValueError):
    pass


def normalize_format(value: str) -> str:
    value = str(value or "").strip().lower()
    value = ALIASES.get(value, value)
    if value not in PRIORITY:
        raise FormatError(f"unsupported format: {value}")
    return value


def format_from_url(url: str, content_type: str = "") -> str | None:
    ctype = str(content_type or "").split(";", 1)[0].strip().lower()
    if ctype in ALIASES:
        return ALIASES[ctype]
    suffix = ""
    try:
        suffix = urlparse(url or "").path.rsplit(".", 1)[-1].lower()
    except Exception:
        return None
    return SUFFIX.get("." + suffix) if suffix else None


def choose_format(
    *,
    best_format: str = "",
    url: str = "",
    content_type: str = "",
    available: list[str] | None = None,
) -> str | None:
    candidates = []
    if best_format:
        try:
            candidates.append(normalize_format(best_format))
        except FormatError:
            pass
    inferred = format_from_url(url, content_type)
    if inferred:
        candidates.append(inferred)
    for value in available or []:
        try:
            candidates.append(normalize_format(value))
        except FormatError:
            continue
    for kind in PRIORITY:
        if kind in candidates:
            return kind
    return None


def resolve_candidate(candidate: dict[str, Any]) -> str | None:
    return choose_format(
        best_format=str(candidate.get("best_format") or ""),
        url=str(candidate.get("url") or ""),
        content_type=str(candidate.get("content_type") or ""),
        available=[str(item) for item in (candidate.get("available_formats") or [])],
    )
