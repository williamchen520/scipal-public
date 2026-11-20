"""N1: independent paper review and publish gate."""

from __future__ import annotations

import json
import os
from typing import Any

import psycopg


class ReviewError(ValueError):
    pass


def _dsn() -> str:
    return (
        os.environ.get("SCIPAL_PAPER_DSN", "").strip()
        or os.environ.get("SCIPAL_PG_OWNER_DSN", "").strip()
        or os.environ.get("SCIPAL_PG_CORPUS_DSN", "").strip()
    )


def quality_summary(
    *,
    title: str,
    abstract: str,
    paragraphs: int,
    sections: int,
    sentences: int,
    code_links: int,
) -> dict[str, Any]:
    issues: list[str] = []
    if len((title or "").strip()) < 10:
        issues.append("title too short")
    if len((abstract or "").strip()) < 100:
        issues.append("abstract too short")
    if paragraphs < 5:
        issues.append(f"too few paragraphs ({paragraphs})")
    if sections < 1:
        issues.append("no sections")
    if sentences < 5:
        issues.append(f"too few sentences ({sentences})")
    return {
        "ok": not issues,
        "issues": issues,
        "metrics": {
            "title_chars": len((title or "").strip()),
            "abstract_chars": len((abstract or "").strip()),
            "paragraphs": paragraphs,
            "sections": sections,
            "sentences": sentences,
            "validated_code_links": code_links,
        },
    }


def ensure_review(paper_id: str, dsn: str = "") -> None:
    dsn = dsn or _dsn()
    if not dsn:
        return
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "INSERT INTO paper_reviews (paper_id,status) VALUES (%s,'draft') "
            "ON CONFLICT (paper_id) DO NOTHING",
            (paper_id,),
        )
        conn.commit()


def _compute_quality(conn, paper_id: str) -> dict[str, Any]:
    paper = conn.execute(
        "SELECT title,abstract,total_paragraphs FROM papers WHERE paper_id=%s",
        (paper_id,),
    ).fetchone()
    if not paper:
        raise ReviewError("paper not found")
    sections = conn.execute(
        "SELECT count(DISTINCT section_path) FROM paragraphs "
        "WHERE paper_id=%s AND section_path IS NOT NULL AND section_path <> ''",
        (paper_id,),
    ).fetchone()[0]
    sentences = conn.execute(
        "SELECT count(*) FROM sentences WHERE paper_id=%s", (paper_id,)
    ).fetchone()[0]
    code_links = conn.execute(
        "SELECT count(*) FROM paper_code_links WHERE paper_id=%s AND status='validated'",
        (paper_id,),
    ).fetchone()[0]
    return quality_summary(
        title=paper[0] or "",
        abstract=paper[1] or "",
        paragraphs=int(paper[2] or 0),
        sections=int(sections or 0),
        sentences=int(sentences or 0),
        code_links=int(code_links or 0),
    )


def _row(row) -> dict[str, Any]:
    return {
        "paper_id": row[0],
        "status": row[1],
        "reviewer": row[2] or "",
        "notes": row[3] or "",
        "quality": row[4] or {},
        "reviewed_at": row[5].isoformat() if row[5] else None,
        "published_at": row[6].isoformat() if row[6] else None,
        "updated_at": row[7].isoformat() if row[7] else None,
    }


def get_review(paper_id: str, dsn: str = "") -> dict[str, Any]:
    dsn = dsn or _dsn()
    if not dsn:
        raise ReviewError("review database not configured")
    ensure_review(paper_id, dsn)
    with psycopg.connect(dsn) as conn:
        quality = _compute_quality(conn, paper_id)
        conn.execute(
            "UPDATE paper_reviews SET quality=%s::jsonb, updated_at=now() WHERE paper_id=%s",
            (json.dumps(quality, ensure_ascii=False), paper_id),
        )
        row = conn.execute(
            "SELECT paper_id,status,reviewer,notes,quality,reviewed_at,published_at,updated_at "
            "FROM paper_reviews WHERE paper_id=%s",
            (paper_id,),
        ).fetchone()
        conn.commit()
    result = _row(row)
    result["quality"] = quality
    return result


def set_decision(
    paper_id: str,
    decision: str,
    *,
    reviewer: str = "",
    notes: str = "",
    force: bool = False,
    dsn: str = "",
) -> dict[str, Any]:
    if decision not in {"approve", "reject"}:
        raise ReviewError("decision must be approve or reject")
    dsn = dsn or _dsn()
    ensure_review(paper_id, dsn)
    status = "reviewed" if decision == "approve" else "rejected"
    quality = get_review(paper_id, dsn)["quality"]
    if decision == "approve" and not quality.get("ok") and not force:
        raise ReviewError("quality gate failed: " + "; ".join(quality.get("issues") or []))
    with psycopg.connect(dsn) as conn:
        current = conn.execute(
            "SELECT status FROM paper_reviews WHERE paper_id=%s", (paper_id,)
        ).fetchone()
        if not current:
            raise ReviewError("paper not found")
        if current[0] == "published":
            raise ReviewError("published paper cannot be re-reviewed")
        conn.execute(
            "UPDATE paper_reviews SET status=%s,reviewer=%s,notes=%s,"
            "reviewed_at=now(),updated_at=now() WHERE paper_id=%s",
            (status, reviewer, notes, paper_id),
        )
        conn.commit()
    return get_review(paper_id, dsn)


def publish(paper_id: str, *, dsn: str = "") -> dict[str, Any]:
    dsn = dsn or _dsn()
    ensure_review(paper_id, dsn)
    with psycopg.connect(dsn) as conn:
        current = conn.execute(
            "SELECT status FROM paper_reviews WHERE paper_id=%s", (paper_id,)
        ).fetchone()
        if not current:
            raise ReviewError("paper not found")
        if current[0] == "published":
            return get_review(paper_id, dsn)
        if current[0] != "reviewed":
            raise ReviewError("only reviewed papers can be published")
        conn.execute(
            "UPDATE paper_reviews SET status='published',published_at=now(),updated_at=now() "
            "WHERE paper_id=%s",
            (paper_id,),
        )
        conn.commit()
    return get_review(paper_id, dsn)


def reset_for_rebuild(paper_id: str, dsn: str = "") -> None:
    """A rebuilt paper must be reviewed again, even if it was published."""
    dsn = dsn or _dsn()
    if not dsn:
        return
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "UPDATE paper_reviews SET status='draft',reviewed_at=NULL,published_at=NULL,"
            "updated_at=now() WHERE paper_id=%s",
            (paper_id,),
        )
        conn.commit()
