"""Paper-lane parsing adapter (staging JSON only)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from services.imports import session
from services.imports.html_quality import QualityRejected
from services.imports.paper_build import paper_id_for
from build_db.parse_service import parse_and_store
from config.settings import DATABASE_PATH
from services.papers.sentences import build_for_paper
from services.pipeline.contracts import SourceRef
from services.pipeline.registry import DEFAULT_REGISTRY


class AdapterUnavailable(RuntimeError):
    """The parsed format has no adapter yet."""


def dsn_owner() -> str:
    return (
        os.environ.get("SCIPAL_PG_OWNER_DSN", "").strip()
        or os.environ.get("SCIPAL_PG_CORPUS_DSN", "").strip()
    )


def _text(node: ET.Element | None) -> str:
    return " ".join("".join(node.itertext()).split()) if node is not None else ""


def _first(node: ET.Element, name: str) -> ET.Element | None:
    for child in node.iter():
        if child.tag.rsplit("}", 1)[-1] == name:
            return child
    return None


def parse_jats(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    sections = []
    for index, sec in enumerate(root.iter()):
        if sec.tag.rsplit("}", 1)[-1] != "sec":
            continue
        title = _text(_first(sec, "title"))
        paragraphs = [
            _text(p)
            for p in sec.iter()
            if p.tag.rsplit("}", 1)[-1] == "p" and _text(p)
        ]
        sections.append(
            {
                "section_id": sec.get("id") or f"sec_{index:03d}",
                "sec_type": sec.get("sec-type") or "",
                "title": title,
                "paragraphs": paragraphs,
            }
        )
    return {
        "source_kind": "jats",
        "article_type": root.get("article-type") or "",
        "title": _text(_first(root, "article-title")),
        "journal": _text(_first(root, "journal-title")),
        "sections": sections,
    }


class PaperLaneAdapter:
    def __init__(self, *, build: bool = False) -> None:
        self.build = build

    def _build_pdf(
        self, item: dict[str, Any], path: Path, *, fallback_from: str = ""
    ) -> str:
        if not self.build:
            raise AdapterUnavailable("pdf adapter requires build=True")
        if os.environ.get("SCIPAL_PDF_FAST", "1") != "0":
            try:
                from services.papers.pdf_fast import try_extract

                fast = try_extract(path)
            except Exception:  # noqa: BLE001 - extraction fallback must not fail import
                fast = None
            if fast:
                paper_id = paper_id_for(item)
                DEFAULT_REGISTRY.sink_for("paper").write(
                    fast,
                    {
                        "paper_id": paper_id,
                        "source_kind": "pdf",
                        "source_uri": item.get("source_uri") or "",
                    },
                )
                sentences = (
                    build_for_paper(paper_id=paper_id, dsn=dsn_owner(), replace=True)
                    if dsn_owner()
                    else {}
                )
                from services.papers.review import ensure_review

                ensure_review(paper_id, dsn_owner() or "")
                payload = {
                    "paper_id": paper_id,
                    "fast": fast,
                    "sentences": sentences,
                }
                session.set_item_parsed(item["import_id"], item["item_id"], payload)
                return "built"
        result = parse_and_store(
            Path(DATABASE_PATH), path, path.name, grobid_mode="auto"
        )
        dsn = (
            os.environ.get("SCIPAL_PG_OWNER_DSN", "").strip()
            or os.environ.get("SCIPAL_PG_CORPUS_DSN", "").strip()
        )
        sentences = (
            build_for_paper(paper_id=result["paper_id"], dsn=dsn, replace=True)
            if dsn
            else {}
        )
        from services.papers.review import ensure_review

        ensure_review(result["paper_id"], dsn or "")
        payload: dict[str, Any] = {
            "paper_id": result["paper_id"],
            "pdf": result,
            "sentences": sentences,
        }
        if fallback_from:
            payload["fallback_from"] = fallback_from
        session.set_item_parsed(item["import_id"], item["item_id"], payload)
        return "built"

    def process(self, item: dict[str, Any]) -> str:
        path = Path(item.get("staged_path") or item.get("source_uri") or "")
        if not path.is_file():
            raise AdapterUnavailable("staged paper file not found")
        kind = item.get("source_kind")
        quality = None
        if kind in {"jats", "html", "md"}:
            try:
                parser = DEFAULT_REGISTRY.parser_for(kind)
                payload = parser.parse(
                    SourceRef(
                        path=path,
                        source_kind=kind,
                        source_uri=item.get("source_uri") or "",
                    )
                )
                gate = DEFAULT_REGISTRY.gate_for(kind)
                if gate is not None:
                    quality = gate.evaluate(payload)
                    payload["quality"] = quality.as_dict()
                    session.set_item_parsed(item["import_id"], item["item_id"], payload)
                    if not quality.ok:
                        raise QualityRejected("; ".join(quality.issues))
            except Exception as exc:
                fallback = str(item.get("fallback_path") or "").strip()
                if self.build and fallback and Path(fallback).is_file():
                    return self._build_pdf(item, Path(fallback), fallback_from="html")
                raise exc
        elif kind == "pdf":
            return self._build_pdf(item, path)
        else:
            raise AdapterUnavailable(f"unsupported paper kind: {kind}")
        session.set_item_parsed(item["import_id"], item["item_id"], payload)
        if quality is not None and not quality.ok:
            raise QualityRejected("; ".join(quality.issues))
        if self.build:
            paper_id = paper_id_for(item)
            DEFAULT_REGISTRY.sink_for("paper").write(
                payload,
                {
                    "paper_id": paper_id,
                    "source_kind": kind,
                    "source_uri": item.get("source_uri") or "",
                },
            )
            payload["paper_id"] = paper_id
            session.set_item_parsed(item["import_id"], item["item_id"], payload)
            return "built"
        return "parsed"
