"""Markdown paper parser for online/repository manuscripts."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
ABSTRACT_TITLES = {"abstract", "summary", "摘要"}


def _front_matter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return {}, text
    data: dict[str, Any] = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            data[key.strip()] = [
                item.strip().strip("'\"") for item in value[1:-1].split(",") if item.strip()
            ]
        elif key.strip() in {"authors", "author"}:
            data[key.strip()] = [item.strip() for item in value.split(",") if item.strip()]
        else:
            data[key.strip()] = value.strip("'\"")
    return data, "\n".join(lines[end + 1 :])


def parse_markdown(path: str | Path | bytes, *, source_uri: str = "") -> dict[str, Any]:
    if isinstance(path, bytes):
        text = path.decode("utf-8", errors="replace")
        filename = Path(source_uri).name if source_uri else "document.md"
        raw = path
    else:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        filename = Path(path).name
        raw = text.encode("utf-8", errors="replace")
    meta, body = _front_matter(text)
    sections: list[dict[str, Any]] = []
    title = str(meta.get("title") or "").strip()
    current_title = ""
    current_paragraphs: list[str] = []
    buffer: list[str] = []

    def flush_paragraph() -> None:
        value = " ".join(line.strip() for line in buffer).strip()
        buffer.clear()
        if value:
            current_paragraphs.append(value)

    def flush_section() -> None:
        nonlocal current_paragraphs
        flush_paragraph()
        if current_paragraphs:
            sections.append(
                {"title": current_title or "(body)", "paragraphs": current_paragraphs}
            )
        current_paragraphs = []

    for line in body.splitlines():
        heading = HEADING_RE.match(line)
        if heading:
            flush_section()
            level = len(heading.group(1))
            value = heading.group(2).strip()
            if level == 1 and not title:
                title = value
                current_title = value
            else:
                current_title = value
            continue
        if not line.strip():
            flush_paragraph()
        else:
            buffer.append(line)
    flush_section()

    abstract = ""
    for section in sections:
        if str(section["title"]).strip().lower() in ABSTRACT_TITLES:
            abstract = " ".join(section["paragraphs"])
            break
    if not abstract:
        for section in sections:
            if section["paragraphs"]:
                abstract = section["paragraphs"][0][:4000]
                break
    doi = str(meta.get("doi") or "").strip()
    if not doi:
        match = DOI_RE.search(body[:8000])
        doi = match.group(0) if match else ""
    authors = meta.get("authors") or meta.get("author") or []
    if isinstance(authors, str):
        authors = [authors]
    title = title or str(meta.get("title") or "") or Path(filename).stem
    return {
        "title": title,
        "doi": doi,
        "abstract": abstract,
        "authors": [str(author) for author in authors if str(author).strip()],
        "journal": str(meta.get("journal") or ""),
        "sections": sections,
        "source_kind": "md",
        "content_hash": hashlib.sha256(raw).hexdigest(),
    }
