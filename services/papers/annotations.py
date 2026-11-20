"""A1: annotation CRUD and target ownership validation."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any

import psycopg

KINDS = {"highlight", "note", "question"}
COLORS = {"yellow", "green", "blue", "red", "purple"}
MAX_COMMENT = 5000
MAX_TAGS = 20


class AnnotationError(ValueError):
    pass


class AnnotationNotFound(AnnotationError):
    pass


class AnnotationConflict(AnnotationError):
    pass


def _dsn() -> str:
    return (
        os.environ.get("SCIPAL_PAPER_DSN", "").strip()
        or os.environ.get("SCIPAL_PG_OWNER_DSN", "").strip()
        or os.environ.get("SCIPAL_PG_CORPUS_DSN", "").strip()
    )


def _clean_tags(tags: Any) -> list[str]:
    if tags is None:
        return []
    if not isinstance(tags, list):
        raise AnnotationError("tags must be a list")
    cleaned = []
    for tag in tags:
        value = str(tag).strip()
        if not value:
            continue
        if len(value) > 40:
            raise AnnotationError("tag too long")
        if value not in cleaned:
            cleaned.append(value)
    if len(cleaned) > MAX_TAGS:
        raise AnnotationError(f"too many tags (max {MAX_TAGS})")
    return cleaned


def _validate_fields(
    *, kind: str, color: str, comment: str, tags: Any
) -> tuple[str, str, str, list[str]]:
    if kind not in KINDS:
        raise AnnotationError("invalid kind")
    if color not in COLORS:
        raise AnnotationError("invalid color")
    comment = str(comment or "")
    if len(comment) > MAX_COMMENT:
        raise AnnotationError("comment too long")
    return kind, color, comment, _clean_tags(tags)


def _validate_target(
    conn,
    *,
    paper_id: str,
    para_id: str,
    sentence_id: str,
    kind: str,
) -> None:
    if not para_id and not sentence_id and kind != "note":
        raise AnnotationError("highlight/question requires a target")
    if not conn.execute(
        "SELECT 1 FROM papers WHERE paper_id=%s", (paper_id,)
    ).fetchone():
        raise AnnotationNotFound("paper not found")
    if para_id:
        row = conn.execute(
            "SELECT paper_id FROM paragraphs WHERE para_id=%s", (para_id,)
        ).fetchone()
        if not row:
            raise AnnotationNotFound("paragraph not found")
        if row[0] != paper_id:
            raise AnnotationConflict("paragraph does not belong to paper")
    if sentence_id:
        row = conn.execute(
            "SELECT paper_id,para_id FROM sentences WHERE sentence_id=%s",
            (sentence_id,),
        ).fetchone()
        if not row:
            raise AnnotationNotFound("sentence not found")
        if row[0] != paper_id:
            raise AnnotationConflict("sentence does not belong to paper")
        if para_id and row[1] and row[1] != para_id:
            raise AnnotationError("sentence does not belong to paragraph")


def _row(row) -> dict[str, Any]:
    return {
        "annotation_id": row[0],
        "paper_id": row[1],
        "para_id": row[2] or "",
        "sentence_id": row[3] or "",
        "kind": row[4],
        "color": row[5],
        "comment": row[6] or "",
        "tags": row[7] or [],
        "created_by": row[8] or "",
        "created_at": row[9].isoformat() if isinstance(row[9], datetime) else row[9],
        "updated_at": row[10].isoformat() if isinstance(row[10], datetime) else row[10],
    }


_COLUMNS = (
    "annotation_id,paper_id,para_id,sentence_id,kind,color,comment,tags,"
    "created_by,created_at,updated_at"
)


def create_annotation(
    *,
    paper_id: str,
    para_id: str = "",
    sentence_id: str = "",
    kind: str = "highlight",
    color: str = "yellow",
    comment: str = "",
    tags: Any = None,
    created_by: str = "",
    dsn: str = "",
) -> dict[str, Any]:
    kind, color, comment, tags = _validate_fields(
        kind=kind, color=color, comment=comment, tags=tags
    )
    dsn = dsn or _dsn()
    if not dsn:
        raise AnnotationError("annotation database not configured")
    annotation_id = "ann_" + uuid.uuid4().hex[:16]
    with psycopg.connect(dsn) as conn:
        _validate_target(
            conn,
            paper_id=paper_id,
            para_id=para_id,
            sentence_id=sentence_id,
            kind=kind,
        )
        row = conn.execute(
            f"INSERT INTO paper_annotations "
            f"(annotation_id,paper_id,para_id,sentence_id,kind,color,comment,tags,created_by) "
            f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s) RETURNING {_COLUMNS}",
            (
                annotation_id,
                paper_id,
                para_id or None,
                sentence_id or None,
                kind,
                color,
                comment,
                json.dumps(tags, ensure_ascii=False),
                created_by,
            ),
        ).fetchone()
        conn.commit()
    return _row(row)


def list_annotations(
    paper_id: str,
    *,
    kind: str = "",
    color: str = "",
    tag: str = "",
    include_deleted: bool = False,
    limit: int = 200,
    dsn: str = "",
) -> list[dict[str, Any]]:
    dsn = dsn or _dsn()
    where = ["paper_id=%s"]
    params: list[Any] = [paper_id]
    if not include_deleted:
        where.append("deleted_at IS NULL")
    if kind:
        where.append("kind=%s")
        params.append(kind)
    if color:
        where.append("color=%s")
        params.append(color)
    if tag:
        where.append("tags ? %s")
        params.append(tag)
    params.append(max(1, min(int(limit), 500)))
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM paper_annotations WHERE {' AND '.join(where)} "
            "ORDER BY created_at DESC LIMIT %s",
            tuple(params),
        ).fetchall()
    return [_row(row) for row in rows]


def update_annotation(
    annotation_id: str,
    *,
    kind: str | None = None,
    color: str | None = None,
    comment: str | None = None,
    tags: Any = None,
    paper_id: str = "",
    dsn: str = "",
) -> dict[str, Any]:
    dsn = dsn or _dsn()
    where = "annotation_id=%s AND deleted_at IS NULL"
    params: list[Any] = [annotation_id]
    if paper_id:
        where += " AND paper_id=%s"
        params.append(paper_id)
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM paper_annotations WHERE {where}",
            tuple(params),
        ).fetchone()
        if not row:
            raise AnnotationNotFound("annotation not found")
        current = _row(row)
        new_kind = kind or current["kind"]
        new_color = color or current["color"]
        new_comment = current["comment"] if comment is None else comment
        new_tags = current["tags"] if tags is None else tags
        new_kind, new_color, new_comment, new_tags = _validate_fields(
            kind=new_kind, color=new_color, comment=new_comment, tags=new_tags
        )
        _validate_target(
            conn,
            paper_id=current["paper_id"],
            para_id=current["para_id"],
            sentence_id=current["sentence_id"],
            kind=new_kind,
        )
        updated = conn.execute(
            f"UPDATE paper_annotations SET kind=%s,color=%s,comment=%s,tags=%s::jsonb,"
            f"updated_at=now() WHERE annotation_id=%s RETURNING {_COLUMNS}",
            (
                new_kind,
                new_color,
                new_comment,
                json.dumps(new_tags, ensure_ascii=False),
                annotation_id,
            ),
        ).fetchone()
        conn.commit()
    return _row(updated)


def delete_annotation(
    annotation_id: str, *, paper_id: str = "", dsn: str = ""
) -> dict[str, Any]:
    dsn = dsn or _dsn()
    where = "annotation_id=%s AND deleted_at IS NULL"
    params: list[Any] = [annotation_id]
    if paper_id:
        where += " AND paper_id=%s"
        params.append(paper_id)
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            f"UPDATE paper_annotations SET deleted_at=now(),updated_at=now() "
            f"WHERE {where} RETURNING annotation_id",
            tuple(params),
        ).fetchone()
        conn.commit()
    if not row:
        raise AnnotationNotFound("annotation not found")
    return {"annotation_id": annotation_id, "deleted": True}
