"""Build paper title/abstract embeddings for S2.3b.

Usage:
    python scripts/build_paper_embeddings.py [--rebuild] [--limit N]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.paths import EMBEDDING_MODEL  # noqa: E402
from services.db.pg_pool import corpus_connection  # noqa: E402


def _literal(values) -> str:
    return "[" + ",".join(f"{float(value):.6f}" for value in values) + "]"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    from sentence_transformers import SentenceTransformer

    model_id = os.environ.get("SCIPAL_EMBEDDING_MODEL", EMBEDDING_MODEL)
    model = SentenceTransformer(model_id)
    conn = corpus_connection()
    try:
        sql = (
            "SELECT p.paper_id, p.title, p.abstract FROM papers p "
            "WHERE p.duplicate_of IS NULL AND p.abstract IS NOT NULL "
            "AND p.abstract <> ''"
        )
        if not args.rebuild:
            sql += (
                " AND NOT EXISTS (SELECT 1 FROM paper_embeddings e "
                "WHERE e.paper_id = p.paper_id AND e.model = %s)"
            )
            params = [model_id]
        else:
            conn.execute("DELETE FROM paper_embeddings WHERE model=%s", (model_id,))
            params = []
        sql += " ORDER BY p.paper_id"
        if args.limit:
            sql += " LIMIT %s"
            params.append(args.limit)
        rows = conn.execute(sql, tuple(params)).fetchall()
        print(f"papers={len(rows)} model={model_id}", flush=True)

        done = 0
        for start in range(0, len(rows), args.batch_size):
            batch = rows[start : start + args.batch_size]
            texts = [
                f"{row['title'] or ''}. {row['abstract'] or ''}".strip()[:4000]
                for row in batch
            ]
            vectors = model.encode(
                texts,
                batch_size=args.batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            for row, vector in zip(batch, vectors):
                conn.execute(
                    "INSERT INTO paper_embeddings(paper_id, model, embedding) "
                    "VALUES (%s, %s, %s::vector) "
                    "ON CONFLICT (paper_id) DO UPDATE SET model=EXCLUDED.model, "
                    "embedding=EXCLUDED.embedding, created_at=now()",
                    (row["paper_id"], model_id, _literal(vector)),
                )
            conn.commit()
            done += len(batch)
            print(f"embedded {done}/{len(rows)}", flush=True)
        print("done", done, flush=True)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
