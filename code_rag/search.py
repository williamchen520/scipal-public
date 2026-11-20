"""Library-scoped hybrid code search over scipal_code (P3)."""

from __future__ import annotations

import argparse
import json
import os
import re
import threading

import psycopg
from sentence_transformers import SentenceTransformer

from code_rag.aliases import expand_query
from code_rag.ranking import path_weight
from code_rag.symbols import normalize_symbol

MODEL = os.environ.get("SCIPAL_CODE_EMBED_MODEL", r"G:/models/bge-small-zh-v1.5")
_MODEL = None
_MODEL_LOCK = threading.Lock()


def get_model():
    global _MODEL
    if _MODEL is None:
        with _MODEL_LOCK:
            if _MODEL is None:
                _MODEL = SentenceTransformer(
                    MODEL, device=os.environ.get("SCIPAL_CODE_DEVICE", "cuda")
                )
    return _MODEL


def reset_model() -> None:
    global _MODEL
    with _MODEL_LOCK:
        _MODEL = None


def _dsn() -> str:
    value = os.environ.get("SCIPAL_CODE_READ_DSN") or os.environ.get("SCIPAL_CODE_DSN", "")
    if not value:
        raise SystemExit("SCIPAL_CODE_READ_DSN or SCIPAL_CODE_DSN is required")
    return value



def active_snapshot(conn, library_id: str) -> str:
    row = conn.execute(
        "SELECT snapshot_id FROM code_rag.code_snapshots "
        "WHERE library_id=%s AND is_active ORDER BY created_at DESC LIMIT 1",
        (library_id,),
    ).fetchone()
    return row[0] if row else ""


def search(
    query: str,
    *,
    library_id: str,
    top_k: int = 10,
    snapshot_id: str = "",
    dsn: str | None = None,
    model: SentenceTransformer | None = None,
) -> list[dict]:
    dsn = dsn or _dsn()
    query = (query or "").strip()[:1000]
    model = model or get_model()
    vector = json.dumps(model.encode([query], normalize_embeddings=True)[0].tolist())
    with psycopg.connect(dsn) as conn:
        if not snapshot_id:
            snapshot_id = active_snapshot(conn, library_id)
            if not snapshot_id:
                return []
        vec = conn.execute(
            """
            SELECT e.unit_id
            FROM code_rag.code_embeddings e
            JOIN code_rag.code_units u ON u.unit_id=e.unit_id
            WHERE u.library_id=%s AND (%s='' OR u.snapshot_id=%s)
              AND u.unit_type <> 'file'
            ORDER BY e.embedding <=> %s::vector
            LIMIT 40
            """,
            (library_id, snapshot_id, snapshot_id, vector),
        ).fetchall()
        lex = conn.execute(
            """
            SELECT unit_id
            FROM code_rag.code_units
            WHERE library_id=%s AND (%s='' OR snapshot_id=%s)
              AND unit_type <> 'file'
              AND GREATEST(
                similarity(symbol_name, %s),
                similarity(left(text, 2000), %s),
                word_similarity(%s, symbol_name)
              ) > 0.02
            ORDER BY GREATEST(
              similarity(symbol_name, %s),
              similarity(left(text, 2000), %s),
              word_similarity(%s, symbol_name)
            ) DESC
            LIMIT 40
            """,
            (library_id, snapshot_id, snapshot_id, query, query, query, query, query, query),
        ).fetchall()
        symbol_norm = normalize_symbol(query)
        symbol_exact = []
        symbol_prefix = []
        if symbol_norm:
            symbol_exact = conn.execute(
                "SELECT unit_id FROM code_rag.code_symbols "
                "WHERE library_id=%s AND snapshot_id=%s AND normalized_name=%s LIMIT 20",
                (library_id, snapshot_id, symbol_norm),
            ).fetchall()
            symbol_prefix = conn.execute(
                "SELECT unit_id FROM code_rag.code_symbols "
                "WHERE library_id=%s AND snapshot_id=%s AND normalized_name LIKE %s "
                "AND normalized_name <> %s LIMIT 50",
                (library_id, snapshot_id, f"{symbol_norm}%", symbol_norm),
            ).fetchall()
        exact = conn.execute(
            """
            SELECT unit_id FROM code_rag.code_units
            WHERE library_id=%s AND (%s='' OR snapshot_id=%s)
              AND (lower(symbol_name)=lower(%s) OR lower(symbol_name)=lower(%s))
            LIMIT 5
            """,
            (
                library_id,
                snapshot_id,
                snapshot_id,
                query,
                query.strip().lower().replace(" ", "_"),
            ),
        ).fetchall()

        expanded = expand_query(query)
        tokens = [
            token
            for token in re.findall(r"[a-z0-9]+", expanded.lower())
            if len(token) >= 3 and token not in {"the", "and", "for", "with", "from", "per"}
        ]
        symbol_rows = []
        if tokens:
            symbol_rows = conn.execute(
                """
                SELECT unit_id, symbol_name FROM code_rag.code_units
                WHERE library_id=%s AND (%s='' OR snapshot_id=%s)
                  AND lower(symbol_name) LIKE ANY(%s)
                LIMIT 2000
                """,
                (library_id, snapshot_id, snapshot_id, [f"%{token}%" for token in tokens]),
            ).fetchall()

        scores: dict[str, float] = {}
        for rank, (unit_id,) in enumerate(vec, 1):
            scores[unit_id] = scores.get(unit_id, 0.0) + 1.0 / (60 + rank)
        for rank, (unit_id,) in enumerate(lex, 1):
            scores[unit_id] = scores.get(unit_id, 0.0) + 1.0 / (60 + rank)
        for unit_id, in exact:
            scores[unit_id] = scores.get(unit_id, 0.0) + 8.0 / 61
        for unit_id, in symbol_exact:
            scores[unit_id] = scores.get(unit_id, 0.0) + 12.0
        for unit_id, in symbol_prefix:
            scores[unit_id] = scores.get(unit_id, 0.0) + 4.0
        query_norm = expanded.strip().lower().replace(" ", "_")
        generic = {"read", "write", "get", "set", "run", "main", "test", "load", "save", "plot"}
        for unit_id, symbol in symbol_rows:
            name = (symbol or "").lower()
            if not name:
                continue
            exact_name = name in tokens
            matched = sum(1 for token in tokens if token in name or token[:5] in name)
            read_verbs = {"read", "load", "open", "parse", "write", "save"}
            if exact_name and len(tokens) == 1 and name not in generic:
                boost = 6.0
            elif exact_name and name in generic:
                boost = 0.3
            elif exact_name:
                boost = 2.0
            elif tokens and tokens[0] in read_verbs and name.startswith(tokens[0]):
                boost = 1.2 + 1.2 * matched / max(len(tokens), 1)
            elif query_norm.startswith(name) or name.startswith(query_norm):
                boost = 1.5
            else:
                boost = 1.2 * matched / max(len(tokens), 1)
            scores[unit_id] = scores.get(unit_id, 0.0) + boost
        if not scores:
            return []
        ids = list(scores)
        rows = conn.execute(
            """
            SELECT u.unit_id, u.library_id, u.snapshot_id, u.symbol_name, u.unit_type,
                   u.text, u.start_line, u.end_line, f.path
            FROM code_rag.code_units u
            JOIN code_rag.code_files f ON f.file_id=u.file_id
            WHERE u.unit_id = ANY(%s)
            """,
            (ids,),
        ).fetchall()
        by_id = {row[0]: row for row in rows}
        path_tokens = set(tokens)
        for unit_id, row in by_id.items():
            path = (row[8] or "").lower()
            path_words = set(re.findall(r"[a-z0-9]+", path))
            path_matches = sum(
                1
                for token in path_tokens
                if token in path_words
                or any(
                    word.startswith(token[:5]) or token.startswith(word[:5])
                    for word in path_words
                    if len(word) >= 4
                )
            )
            path_boost = 1.0 + 0.5 * path_matches / max(len(path_tokens), 1)
            scores[unit_id] *= path_weight(query, path) * path_boost
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
    result = []
    for unit_id, score in ordered:
        row = by_id.get(unit_id)
        if not row:
            continue
        result.append(
            {
                "unit_id": row[0],
                "library_id": row[1],
                "snapshot_id": row[2],
                "symbol_name": row[3],
                "unit_type": row[4],
                "snippet": (row[5] or "")[:500],
                "start_line": row[6],
                "end_line": row[7],
                "path": row[8],
                "score": score,
            }
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--library-id", required=True)
    parser.add_argument("--snapshot-id", default="")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    hits = search(
        args.query,
        library_id=args.library_id,
        top_k=args.top_k,
        snapshot_id=args.snapshot_id,
    )
    if args.json:
        print(json.dumps({"query": args.query, "library_id": args.library_id, "hits": hits}, ensure_ascii=False, indent=2))
    else:
        for i, hit in enumerate(hits, 1):
            print(f"{i}. {hit['symbol_name']} [{hit['unit_type']}] {hit['path']}:{hit['start_line']} score={hit['score']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
