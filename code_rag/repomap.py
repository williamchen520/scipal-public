"""Repository map: rank files by code-graph centrality under a token budget."""

from __future__ import annotations

import argparse
import json
import math
import os
from collections import defaultdict
from typing import Any

import psycopg

from code_rag.symbols import normalize_symbol


def _dsn() -> str:
    value = os.environ.get("SCIPAL_CODE_READ_DSN") or os.environ.get("SCIPAL_CODE_DSN", "")
    if not value:
        raise SystemExit("SCIPAL_CODE_READ_DSN or SCIPAL_CODE_DSN is required")
    return value


def rollup_graph(
    units: list[tuple[str, str, str, str]],
    edges: list[tuple[str, str, str]],
    seeds: dict[str, float] | None = None,
) -> tuple[dict[str, float], dict[str, list[str]]]:
    """Pure file-level graph rollup + PageRank. units=(unit_id,path,symbol,type)."""
    unit_path = {unit_id: path for unit_id, path, _, _ in units}
    symbols: dict[str, list[str]] = defaultdict(list)
    for _, path, symbol, _ in units:
        if symbol and symbol not in symbols[path]:
            symbols[path].append(symbol)
    graph: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for src, dst, relation in edges:
        source, target = unit_path.get(src), unit_path.get(dst)
        if not source or not target or source == target:
            continue
        weight = 2.0 if relation in {"calls", "imports"} else 1.0
        graph[source][target] += weight
    paths = sorted({path for _, path, _, _ in units})
    if not paths:
        return {}, {}
    n = len(paths)
    base = {path: 1.0 / n for path in paths}
    if seeds:
        total_seed = sum(max(0.0, seed) for seed in seeds.values())
        if total_seed > 0:
            base = {path: max(0.0, seeds.get(path, 0.0)) / total_seed for path in paths}
    rank = dict(base)
    for _ in range(20):
        updated = {path: 0.15 * base[path] for path in paths}
        for source in paths:
            targets = graph.get(source, {})
            total = sum(targets.values())
            if not total:
                continue
            for target, weight in targets.items():
                updated[target] += 0.85 * rank[source] * weight / total
        rank = updated
    return rank, symbols


def build_repomap(
    *,
    library_id: str,
    snapshot_id: str = "",
    max_tokens: int = 2000,
    max_symbols_per_file: int = 12,
    query: str = "",
    dsn: str | None = None,
) -> dict[str, Any]:
    dsn = dsn or _dsn()
    with psycopg.connect(dsn) as conn:
        if not snapshot_id:
            row = conn.execute(
                "SELECT snapshot_id FROM code_rag.code_snapshots "
                "WHERE library_id=%s AND is_active LIMIT 1",
                (library_id,),
            ).fetchone()
            snapshot_id = row[0] if row else ""
        if not snapshot_id:
            return {"library_id": library_id, "snapshot_id": "", "files": [], "text": "", "tokens_est": 0}
        units = conn.execute(
            "SELECT u.unit_id, f.path, u.symbol_name, u.unit_type "
            "FROM code_rag.code_units u JOIN code_rag.code_files f ON f.file_id=u.file_id "
            "WHERE u.library_id=%s AND u.snapshot_id=%s AND u.unit_type <> 'file'",
            (library_id, snapshot_id),
        ).fetchall()
        edges = conn.execute(
            "SELECT e.src_unit_id,e.dst_unit_id,e.relation FROM code_rag.code_edges e "
            "JOIN code_rag.code_units s ON s.unit_id=e.src_unit_id "
            "JOIN code_rag.code_units d ON d.unit_id=e.dst_unit_id "
            "WHERE e.library_id=%s AND s.snapshot_id=%s AND d.snapshot_id=%s",
            (library_id, snapshot_id, snapshot_id),
        ).fetchall()
    seeds: dict[str, float] = {}
    query_norm = normalize_symbol(query)
    if query_norm:
        query_terms = set(query_norm.split())
        for _, path, symbol, _ in units:
            symbol_norm = normalize_symbol(symbol)
            score = 0.0
            if symbol_norm == query_norm:
                score += 6.0
            elif query_norm and symbol_norm.startswith(query_norm):
                score += 3.0
            matched = len(query_terms & set(symbol_norm.split()))
            if matched:
                score += 1.5 * matched / max(len(query_terms), 1)
            path_terms = set(normalize_symbol(path).split())
            path_matched = len(query_terms & path_terms)
            if path_matched:
                score += 0.5 * path_matched / max(len(query_terms), 1)
            if score:
                seeds[path] = max(seeds.get(path, 0.0), score)
    rank, symbols = rollup_graph(
        [tuple(row) for row in units], [tuple(row) for row in edges], seeds or None
    )
    ordered = sorted(
        rank,
        key=lambda path: (rank[path], len(symbols.get(path, []))),
        reverse=True,
    )
    budget = max(200, min(int(max_tokens), 20000))
    lines: list[str] = []
    selected: list[dict[str, Any]] = []
    used = 0
    for path in ordered:
        names = symbols.get(path, [])[:max_symbols_per_file]
        line = f"{path}: " + ", ".join(names)
        cost = max(1, math.ceil(len(line) / 4))
        if used + cost > budget:
            break
        lines.append(line)
        selected.append({"path": path, "score": round(rank[path], 6), "symbols": names})
        used += cost
    return {
        "library_id": library_id,
        "snapshot_id": snapshot_id,
        "files": selected,
        "text": "\n".join(lines),
        "tokens_est": used,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library-id", required=True)
    parser.add_argument("--snapshot-id", default="")
    parser.add_argument("--max-tokens", type=int, default=2000)
    parser.add_argument("--query", default="")
    parser.add_argument("--dsn", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = build_repomap(
        library_id=args.library_id,
        snapshot_id=args.snapshot_id,
        max_tokens=args.max_tokens,
        query=args.query,
        dsn=args.dsn or None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result["text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
