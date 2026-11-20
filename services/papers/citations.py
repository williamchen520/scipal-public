"""B0.5: citation edge writes and cross_paper_index projection."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

import psycopg


class CitationError(ValueError):
    pass


def _dsn() -> str:
    return (
        os.environ.get("SCIPAL_PAPER_DSN", "").strip()
        or os.environ.get("SCIPAL_PG_OWNER_DSN", "").strip()
        or os.environ.get("SCIPAL_PG_CORPUS_DSN", "").strip()
    )


def _project(conn, edge: dict[str, Any]) -> bool:
    edge_id = edge["edge_id"]
    src = edge.get("src_paper_id") or ""
    dst = edge.get("dst_paper_id") or ""
    if not src or not dst:
        conn.execute("DELETE FROM cross_paper_index WHERE link_id=%s", (edge_id,))
        return False
    conn.execute(
        "INSERT INTO cross_paper_index "
        "(link_id,source_paper_id,target_paper_id,relation,confidence) "
        "VALUES (%s,%s,%s,%s,1.0) "
        "ON CONFLICT (link_id) DO UPDATE SET "
        "source_paper_id=EXCLUDED.source_paper_id,"
        "target_paper_id=EXCLUDED.target_paper_id,"
        "relation=EXCLUDED.relation,"
        "confidence=EXCLUDED.confidence",
        (edge_id, src, dst, edge.get("relation") or "cites"),
    )
    return True


def _row(row) -> dict[str, Any]:
    return {
        "edge_id": row[0],
        "src_paper_id": row[1] or "",
        "dst_paper_id": row[2] or "",
        "src_doi": row[3] or "",
        "dst_doi": row[4] or "",
        "src_external_source": row[5] or "",
        "src_external_id": row[6] or "",
        "dst_external_source": row[7] or "",
        "dst_external_id": row[8] or "",
        "dst_title": row[9] or "",
        "dst_year": row[10] or "",
        "source": row[11],
        "relation": row[12],
        "provenance": row[13] or {},
        "projected": bool(row[14]),
    }


_COLUMNS = (
    "e.edge_id,e.src_paper_id,e.dst_paper_id,e.src_doi,e.dst_doi,"
    "e.src_external_source,e.src_external_id,e.dst_external_source,e.dst_external_id,"
    "e.dst_title,e.dst_year,e.source,e.relation,e.provenance,"
    "(c.link_id IS NOT NULL)"
)


def upsert_edge(
    *,
    source: str,
    src_paper_id: str = "",
    dst_paper_id: str = "",
    src_doi: str = "",
    dst_doi: str = "",
    src_external_source: str = "",
    src_external_id: str = "",
    dst_external_source: str = "",
    dst_external_id: str = "",
    dst_title: str = "",
    dst_year: str = "",
    relation: str = "cites",
    provenance: dict[str, Any] | None = None,
    edge_id: str = "",
    dsn: str = "",
) -> dict[str, Any]:
    if not source:
        raise CitationError("source is required")
    if not (
        dst_paper_id or dst_doi or dst_external_id or dst_title
    ):
        raise CitationError("destination is required")
    dsn = dsn or _dsn()
    edge_id = edge_id or "edge_" + uuid.uuid4().hex[:16]
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            "INSERT INTO paper_citation_edges "
            "(edge_id,src_paper_id,dst_paper_id,src_doi,dst_doi,"
            "src_external_source,src_external_id,dst_external_source,dst_external_id,"
            "dst_title,dst_year,source,relation,provenance) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) "
            "ON CONFLICT (edge_id) DO UPDATE SET "
            "src_paper_id=EXCLUDED.src_paper_id,dst_paper_id=EXCLUDED.dst_paper_id,"
            "src_doi=EXCLUDED.src_doi,dst_doi=EXCLUDED.dst_doi,"
            "src_external_source=EXCLUDED.src_external_source,"
            "src_external_id=EXCLUDED.src_external_id,"
            "dst_external_source=EXCLUDED.dst_external_source,"
            "dst_external_id=EXCLUDED.dst_external_id,"
            "dst_title=EXCLUDED.dst_title,dst_year=EXCLUDED.dst_year,"
            "source=EXCLUDED.source,relation=EXCLUDED.relation,"
            "provenance=EXCLUDED.provenance "
            "RETURNING edge_id",
            (
                edge_id,
                src_paper_id or None,
                dst_paper_id or None,
                src_doi or None,
                dst_doi or None,
                src_external_source or None,
                src_external_id or None,
                dst_external_source or None,
                dst_external_id or None,
                dst_title or None,
                dst_year or None,
                source,
                relation,
                json.dumps(provenance or {}, ensure_ascii=False),
            ),
        ).fetchone()
        _project(
            conn,
            {
                "edge_id": row[0],
                "src_paper_id": src_paper_id,
                "dst_paper_id": dst_paper_id,
                "relation": relation,
            },
        )
        conn.commit()
        return get_edge(row[0], dsn=dsn)


def get_edge(edge_id: str, *, dsn: str = "") -> dict[str, Any]:
    dsn = dsn or _dsn()
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM paper_citation_edges e "
            "LEFT JOIN cross_paper_index c ON c.link_id=e.edge_id "
            "WHERE e.edge_id=%s",
            (edge_id,),
        ).fetchone()
    if not row:
        raise CitationError("edge not found")
    return _row(row)


def delete_edge(edge_id: str, *, dsn: str = "") -> dict[str, Any]:
    dsn = dsn or _dsn()
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            "DELETE FROM paper_citation_edges WHERE edge_id=%s RETURNING edge_id",
            (edge_id,),
        ).fetchone()
        conn.execute("DELETE FROM cross_paper_index WHERE link_id=%s", (edge_id,))
        conn.commit()
    if not row:
        raise CitationError("edge not found")
    return {"edge_id": edge_id, "deleted": True}


def reproject_all(*, dsn: str = "") -> dict[str, int]:
    dsn = dsn or _dsn()
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            "SELECT edge_id,src_paper_id,dst_paper_id,relation FROM paper_citation_edges"
        ).fetchall()
        projected = 0
        for edge in rows:
            projected += int(
                _project(
                    conn,
                    {
                        "edge_id": edge[0],
                        "src_paper_id": edge[1],
                        "dst_paper_id": edge[2],
                        "relation": edge[3],
                    },
                )
            )
        conn.commit()
    return {"edges": len(rows), "projected": projected}


def list_references(paper_id: str, *, limit: int = 200, dsn: str = "") -> list[dict[str, Any]]:
    return _list_edges("e.src_paper_id", paper_id, limit=limit, dsn=dsn)


def list_citations(paper_id: str, *, limit: int = 200, dsn: str = "") -> list[dict[str, Any]]:
    return _list_edges("e.dst_paper_id", paper_id, limit=limit, dsn=dsn)


def _list_edges(
    column: str, paper_id: str, *, limit: int = 200, dsn: str = ""
) -> list[dict[str, Any]]:
    dsn = dsn or _dsn()
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM paper_citation_edges e "
            "LEFT JOIN cross_paper_index c ON c.link_id=e.edge_id "
            f"WHERE {column}=%s ORDER BY e.created_at DESC LIMIT %s",
            (paper_id, max(1, min(int(limit), 500))),
        ).fetchall()
    return [_row(row) for row in rows]


def resolve_local_destinations(*, dsn: str = "") -> dict[str, int]:
    """Fill dst_paper_id for edges whose DOI or external ID matches a local paper."""
    dsn = dsn or _dsn()
    resolved: set[str] = set()
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            "UPDATE paper_citation_edges e SET dst_paper_id=("
            "  SELECT p.paper_id FROM papers p "
            "  WHERE lower(p.doi)=lower(e.dst_doi) "
            "  ORDER BY (p.duplicate_of IS NULL) DESC, p.paper_id LIMIT 1"
            ") "
            "WHERE e.dst_paper_id IS NULL AND e.dst_doi IS NOT NULL "
            "AND EXISTS (SELECT 1 FROM papers p WHERE lower(p.doi)=lower(e.dst_doi)) "
            "RETURNING e.edge_id"
        ).fetchall()
        resolved.update(row[0] for row in rows)
        rows = conn.execute(
            "UPDATE paper_citation_edges e SET dst_paper_id=("
            "  SELECT x.paper_id FROM paper_external_ids x "
            "  WHERE x.source=e.dst_external_source AND x.external_id=e.dst_external_id "
            "  ORDER BY x.confidence DESC, x.paper_id LIMIT 1"
            ") "
            "WHERE e.dst_paper_id IS NULL AND e.dst_external_source IS NOT NULL "
            "AND e.dst_external_id IS NOT NULL "
            "AND EXISTS (SELECT 1 FROM paper_external_ids x "
            "            WHERE x.source=e.dst_external_source "
            "            AND x.external_id=e.dst_external_id) "
            "RETURNING e.edge_id"
        ).fetchall()
        resolved.update(row[0] for row in rows)
        for edge_id in resolved:
            edge = conn.execute(
                "SELECT edge_id,src_paper_id,dst_paper_id,relation "
                "FROM paper_citation_edges WHERE edge_id=%s",
                (edge_id,),
            ).fetchone()
            if edge:
                _project(
                    conn,
                    {
                        "edge_id": edge[0],
                        "src_paper_id": edge[1],
                        "dst_paper_id": edge[2],
                        "relation": edge[3],
                    },
                )
        conn.commit()
    return {"resolved": len(resolved), "projected": len(resolved)}
