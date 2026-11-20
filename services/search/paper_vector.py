"""S2.3b: paper title/abstract vector search."""

from __future__ import annotations

import os
from typing import List, Optional

from services.search.pg_vector import vector_literal


class PaperVectorSearch:
    def __init__(self, dsn: Optional[str] = None, *, connector=None):
        self.dsn = dsn
        self._connector = connector

    def _connection(self):
        if self._connector is not None:
            return self._connector(), False
        from services.db.pg_pool import corpus_connection, pg_connection

        return (pg_connection(self.dsn) if self.dsn else corpus_connection()), True

    def search(self, query_embedding, *, top_k: int = 8) -> List[dict]:
        if query_embedding is None or len(query_embedding) == 0:
            return []
        literal = vector_literal(query_embedding)
        pg, close = self._connection()
        try:
            try:
                ef_search = max(
                    1, min(1000, int(os.environ.get("SCIPAL_PGVECTOR_EF_SEARCH", "200")))
                )
            except ValueError:
                ef_search = 100
            pg.execute(f"SET hnsw.ef_search = {ef_search}")
            rows = pg.execute(
                "SELECT e.paper_id, 1 - (e.embedding <=> %s::vector) AS rank "
                "FROM paper_embeddings e JOIN papers p ON p.paper_id=e.paper_id "
                "WHERE p.duplicate_of IS NULL "
                "ORDER BY e.embedding <=> %s::vector, e.paper_id LIMIT %s",
                (literal, literal, top_k),
            ).fetchall()
        finally:
            if close:
                pg.close()
        return [dict(row) for row in rows]
