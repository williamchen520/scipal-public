"""Build a per-library smoke set: Python docstrings, R/Nextflow symbol phrases."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import psycopg

LIBS = {
    "lib_2c5709b07c77": "python",
    "lib_anndata": "python",
    "lib_squidpy": "python",
    "lib_scvi_tools": "python",
    "lib_snakemake": "python",
    "lib_ggplot2": "r",
    "lib_dplyr": "r",
    "lib_12473817b941": "nextflow",
    "lib_nfcore_scrnaseq": "nextflow",
    "lib_nfcore_atacseq": "nextflow",
}
DOC = re.compile(r'[rRuU]?["\']{3}(.*?)["\']{3}', re.S)


def doc_query(text: str) -> str:
    match = DOC.search(text or "")
    if not match:
        return ""
    body = match.group(1)
    body = re.sub(r"\.\. [^\n]+", " ", body)
    body = re.sub(r":[a-z]+:.*", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    sentences = re.split(r"(?<=[.!?])\s+", body)
    query = sentences[0] if sentences else body
    words = query.split()
    return " ".join(words[:24]).strip(" `.,:;")


def symbol_query(symbol: str) -> str:
    return re.sub(r"[_\-.]+", " ", symbol).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="eval/code_rag_stack/per_library_10.json")
    parser.add_argument("--per-library", type=int, default=10)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_CODE_READ_DSN", ""))
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_CODE_READ_DSN is required")
    cases = []
    with psycopg.connect(args.dsn) as conn:
        for library_id, language in LIBS.items():
            rows = conn.execute(
                "SELECT u.symbol_name,u.unit_type,u.text,f.path "
                "FROM code_rag.code_units u "
                "JOIN code_rag.code_files f ON f.file_id=u.file_id "
                "JOIN code_rag.code_snapshots s ON s.snapshot_id=u.snapshot_id AND s.is_active "
                "WHERE u.library_id=%s AND u.unit_type IN ('function','class','process') "
                "AND f.path NOT LIKE 'tests/%%' AND f.path NOT LIKE 'test/%%' "
                "ORDER BY u.symbol_name",
                (library_id,),
            ).fetchall()
            chosen = []
            for symbol, unit_type, text, path in rows[args.offset:]:
                if symbol.startswith("_") or "__" in symbol:
                    continue
                query = doc_query(text) if language == "python" else symbol_query(symbol)
                if len(query.split()) < 2 or len(query) > 180:
                    continue
                if any(item["query"].lower() == query.lower() for item in chosen):
                    continue
                chosen.append(
                    {
                        "id": f"{library_id.replace('lib_', '')}_{len(chosen) + 1:02d}",
                        "library_id": library_id,
                        "language": language,
                        "category": "docstring" if language == "python" else "symbol-smoke",
                        "query": query,
                        "expected_symbol": symbol,
                        "expected_path": path,
                    }
                )
                if len(chosen) >= args.per_library:
                    break
            print(library_id, len(chosen))
            cases.extend(chosen)
    Path(args.output).write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"WROTE {args.output} cases={len(cases)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
