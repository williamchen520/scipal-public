"""Ingest one pinned repository into scipal_code (P2).

No embeddings yet: P2 is AST/tree-sitter boundaries and graph edges.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

import psycopg

from code_rag.parsers import (
    parse_javascript,
    parse_nextflow,
    parse_python,
    parse_r,
    parse_rmd,
    parse_typescript,
)
from code_rag.environments import record as record_environment
from code_rag.source_meta import detect_license, is_generated, is_vendored, scan_secrets
from code_rag.symbols import normalize_symbol


def stable(prefix: str, *parts: str) -> str:
    return prefix + "_" + hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def repo_commit(path: Path) -> str:
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def scoped_unit_id(library_id: str, snapshot_id: str, parsed_unit_id: str) -> str:
    """Unit ids must not collide when two libraries contain the same path."""
    return stable("unit", library_id, snapshot_id, parsed_unit_id)


def file_language(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return "python"
    if suffix in {".r", ".rmd", ".qmd"}:
        return "rmd" if suffix in {".rmd", ".qmd"} else "r"
    if suffix in {".js", ".jsx", ".mjs", ".cjs"}:
        return "javascript"
    if suffix in {".ts", ".tsx"}:
        return "typescript"
    if suffix == ".nf" or path.name == "nextflow.config":
        return "nextflow"
    return "unknown"


def files_for(repo: Path, language: str, limit: int) -> list[Path]:
    if language == "auto":
        patterns = [
            "**/*.py", "**/*.js", "**/*.jsx", "**/*.mjs", "**/*.cjs",
            "**/*.ts", "**/*.tsx", "**/*.R", "**/*.r", "**/*.Rmd",
            "**/*.qmd", "**/*.nf", "**/nextflow.config",
        ]
    elif language == "python":
        patterns = ["**/*.py"]
    elif language == "nextflow":
        patterns = ["**/*.nf", "**/nextflow.config", "**/*.config"]
    elif language == "r":
        patterns = ["**/*.R", "**/*.r"]
    elif language == "javascript":
        patterns = ["**/*.js", "**/*.jsx", "**/*.mjs", "**/*.cjs"]
    elif language == "typescript":
        patterns = ["**/*.ts", "**/*.tsx"]
    elif language == "rmd":
        patterns = ["**/*.Rmd", "**/*.qmd"]
    else:
        raise SystemExit(f"unsupported language: {language}")
    found = []
    for pattern in patterns:
        found.extend(repo.glob(pattern))
    result = []
    skip_parts = {".git", "__pycache__", "site-packages", "node_modules", ".venv", "dist"}
    for path in sorted(set(found)):
        if any(part in skip_parts or part.startswith("venv") for part in path.parts):
            continue
        result.append(path)
        if limit and len(result) >= limit:
            break
    return result



def record_symbol(
    conn,
    *,
    unit_id: str,
    library_id: str,
    snapshot_id: str,
    symbol_name: str,
    path: str,
    unit_type: str,
    start_line: int,
    end_line: int,
) -> None:
    conn.execute(
        "INSERT INTO code_rag.code_symbols "
        "(unit_id,library_id,snapshot_id,symbol_name,normalized_name,path,unit_type,"
        "start_line,end_line) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (unit_id) DO UPDATE SET normalized_name=EXCLUDED.normalized_name",
        (
            unit_id, library_id, snapshot_id, symbol_name,
            normalize_symbol(symbol_name), path, unit_type, start_line, end_line,
        ),
    )

def copy_unchanged_file(
    conn,
    *,
    old_file_id: str,
    new_file_id: str,
    rel: str,
    language: str,
    digest: str,
    library_id: str,
    snapshot_id: str,
    generated: bool = False,
    vendored: bool = False,
) -> int:
    """Copy an unchanged file and its units/edges/embeddings to a new snapshot."""
    conn.execute(
        "INSERT INTO code_rag.code_files "
        "(file_id,snapshot_id,library_id,path,language,content_hash,"
        "is_generated,is_vendored) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (snapshot_id,path) DO NOTHING",
        (new_file_id, snapshot_id, library_id, rel, language, digest, generated, vendored),
    )
    old_units = conn.execute(
        "SELECT unit_id,symbol_name,unit_type,text,start_line,end_line,parent_unit_id "
        "FROM code_rag.code_units WHERE file_id=%s",
        (old_file_id,),
    ).fetchall()
    id_map = {}
    for row in old_units:
        new_id = scoped_unit_id(library_id, snapshot_id, row[0])
        id_map[row[0]] = new_id
        parent = id_map.get(row[6], row[6])
        conn.execute(
            "INSERT INTO code_rag.code_units "
            "(unit_id,snapshot_id,library_id,file_id,symbol_name,unit_type,text,"
            "start_line,end_line,parent_unit_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (unit_id) DO NOTHING",
            (new_id, snapshot_id, library_id, new_file_id, row[1], row[2], row[3],
             row[4], row[5], parent),
        )
        record_symbol(
            conn, unit_id=new_id, library_id=library_id, snapshot_id=snapshot_id,
            symbol_name=row[1], path=rel, unit_type=row[2],
            start_line=row[4], end_line=row[5],
        )
    if id_map:
        old_ids = list(id_map)
        edges = conn.execute(
            "SELECT src_unit_id,dst_unit_id,relation,source,confidence "
            "FROM code_rag.code_edges WHERE src_unit_id = ANY(%s) OR dst_unit_id = ANY(%s)",
            (old_ids, old_ids),
        ).fetchall()
        for src, dst, relation, source, confidence in edges:
            if src not in id_map or dst not in id_map:
                continue
            conn.execute(
                "INSERT INTO code_rag.code_edges "
                "(src_unit_id,dst_unit_id,library_id,relation,source,confidence) "
                "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (id_map[src], id_map[dst], library_id, relation, source, confidence),
            )
        for old_id, new_id in id_map.items():
            conn.execute(
                "INSERT INTO code_rag.code_embeddings "
                "(unit_id,library_id,model,embedding) "
                "SELECT %s, library_id, model, embedding FROM code_rag.code_embeddings "
                "WHERE unit_id=%s ON CONFLICT (unit_id) DO NOTHING",
                (new_id, old_id),
            )
    return len(old_units)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--library-id", required=True)
    parser.add_argument("--repo-url", required=True)
    parser.add_argument("--ref", default="")
    parser.add_argument(
        "--language",
        choices=["python", "nextflow", "r", "rmd", "javascript", "typescript", "auto"],
        required=True,
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--full", action="store_true", help="reparse unchanged files")
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_CODE_DSN", ""))
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_CODE_DSN is required")
    repo = Path(args.repo)
    commit = repo_commit(repo)
    source_id = stable("src", args.library_id, args.repo_url)
    snapshot_id = stable("snap", source_id, commit)
    files = files_for(repo, args.language, args.limit)
    license_id = detect_license(repo)

    with psycopg.connect(args.dsn) as conn:
        conn.execute(
            """
            INSERT INTO code_rag.code_sources (source_id, library_id, repo_url, ref, license)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (source_id) DO UPDATE SET ref=EXCLUDED.ref, license=EXCLUDED.license
            """,
            (source_id, args.library_id, args.repo_url, args.ref, license_id),
        )
        prev_row = conn.execute(
            "SELECT snapshot_id FROM code_rag.code_snapshots "
            "WHERE library_id=%s AND is_active LIMIT 1",
            (args.library_id,),
        ).fetchone()
        prev_snapshot = prev_row[0] if prev_row else ""
        conn.execute(
            "UPDATE code_rag.code_snapshots SET is_active=false WHERE library_id=%s",
            (args.library_id,),
        )
        conn.execute(
            """
            INSERT INTO code_rag.code_snapshots
              (snapshot_id, source_id, library_id, commit_sha, ref, is_active)
            VALUES (%s,%s,%s,%s,%s,true)
            ON CONFLICT (snapshot_id) DO UPDATE SET is_active=true,
              ref=EXCLUDED.ref
            """,
            (snapshot_id, source_id, args.library_id, commit, args.ref),
        )
        environment = record_environment(
            conn,
            library_id=args.library_id,
            snapshot_id=snapshot_id,
            repo=repo,
            language=args.language,
            ref=commit,
        )
        same_snapshot = prev_snapshot == snapshot_id
        existing = {}
        prev_files = {}
        if same_snapshot:
            existing = {
                row[0]: (row[1], row[2])
                for row in conn.execute(
                    "SELECT path,file_id,content_hash FROM code_rag.code_files "
                    "WHERE snapshot_id=%s",
                    (snapshot_id,),
                ).fetchall()
            }
        elif prev_snapshot:
            prev_files = {
                row[0]: (row[1], row[2], row[3])
                for row in conn.execute(
                    "SELECT path,file_id,content_hash,language FROM code_rag.code_files "
                    "WHERE snapshot_id=%s",
                    (prev_snapshot,),
                ).fetchall()
            }
        prepared = []
        secret_skipped = 0
        for path in files:
            rel = path.relative_to(repo).as_posix()
            text = path.read_text(encoding="utf-8", errors="ignore")
            if scan_secrets(text):
                secret_skipped += 1
                continue
            digest = hashlib.sha256(text.encode()).hexdigest()
            prepared.append((path, rel, text, digest))
        current_paths = {rel for _, rel, _, _ in prepared}
        if not same_snapshot:
            existing = {}
        for rel, (old_file_id, _) in existing.items():
            if rel in current_paths:
                continue
            old_units = [
                row[0]
                for row in conn.execute(
                    "SELECT unit_id FROM code_rag.code_units WHERE file_id=%s",
                    (old_file_id,),
                ).fetchall()
            ]
            if old_units:
                conn.execute(
                    "DELETE FROM code_rag.code_edges WHERE src_unit_id = ANY(%s) "
                    "OR dst_unit_id = ANY(%s)",
                    (old_units, old_units),
                )
            conn.execute("DELETE FROM code_rag.code_units WHERE file_id=%s", (old_file_id,))
            conn.execute("DELETE FROM code_rag.code_files WHERE file_id=%s", (old_file_id,))
        run = conn.execute(
            "INSERT INTO code_rag.code_ingest_runs (library_id,snapshot_id,status) "
            "VALUES (%s,%s,'running') RETURNING run_id",
            (args.library_id, snapshot_id),
        ).fetchone()[0]

        total_units = total_edges = skipped = copied = 0
        for index, (path, rel, text, digest) in enumerate(prepared, start=1):
            old = existing.get(rel)
            previous = prev_files.get(rel)
            if not args.full and previous and previous[1] == digest:
                new_file_id = stable("file", snapshot_id, rel)
                total_units += copy_unchanged_file(
                    conn,
                    old_file_id=previous[0],
                    new_file_id=new_file_id,
                    rel=rel,
                    language=previous[2],
                    digest=digest,
                    library_id=args.library_id,
                    snapshot_id=snapshot_id,
                    generated=is_generated(rel),
                    vendored=is_vendored(rel),
                )
                copied += 1
                continue
            if not args.full and old and old[1] == digest:
                skipped += 1
                continue
            if old:
                old_file_id = old[0]
                old_units = [
                    row[0]
                    for row in conn.execute(
                        "SELECT unit_id FROM code_rag.code_units WHERE file_id=%s",
                        (old_file_id,),
                    ).fetchall()
                ]
                if old_units:
                    conn.execute(
                        "DELETE FROM code_rag.code_edges WHERE src_unit_id = ANY(%s) "
                        "OR dst_unit_id = ANY(%s)",
                        (old_units, old_units),
                    )
                conn.execute("DELETE FROM code_rag.code_units WHERE file_id=%s", (old_file_id,))
            language = file_language(path) if args.language == "auto" else args.language
            if language == "python":
                units, edges = parse_python(text, rel)
            elif language == "r":
                units, edges = parse_r(text, rel)
            elif language == "rmd":
                units, edges = parse_rmd(text, rel)
            elif language == "nextflow":
                units, edges = parse_nextflow(text, rel)
            elif language == "javascript":
                units, edges = parse_javascript(text, rel)
            elif language == "typescript":
                units, edges = parse_typescript(text, rel)
            else:
                units, edges = parse_rmd(text, rel)
            file_id = stable("file", snapshot_id, rel)
            conn.execute(
                """
                INSERT INTO code_rag.code_files
                  (file_id, snapshot_id, library_id, path, language, content_hash,
                   is_generated, is_vendored)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (snapshot_id, path) DO UPDATE SET
                  content_hash=EXCLUDED.content_hash,
                  is_generated=EXCLUDED.is_generated,
                  is_vendored=EXCLUDED.is_vendored
                """,
                (
                    file_id,
                    snapshot_id,
                    args.library_id,
                    rel,
                    language,
                    hashlib.sha256(text.encode()).hexdigest(),
                    is_generated(rel),
                    is_vendored(rel),
                ),
            )
            unit_ids = {
                unit.unit_id: scoped_unit_id(args.library_id, snapshot_id, unit.unit_id)
                for unit in units
            }
            for unit in units:
                conn.execute(
                    """
                    INSERT INTO code_rag.code_units
                      (unit_id, snapshot_id, library_id, file_id, symbol_name,
                       unit_type, text, start_line, end_line, parent_unit_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (unit_id) DO NOTHING
                    """,
                    (
                        unit_ids[unit.unit_id],
                        snapshot_id,
                        args.library_id,
                        file_id,
                        unit.symbol_name,
                        unit.unit_type,
                        unit.text,
                        unit.start_line,
                        unit.end_line,
                        unit_ids.get(unit.parent_unit_id, unit.parent_unit_id),
                    ),
                )
                record_symbol(
                    conn,
                    unit_id=unit_ids[unit.unit_id],
                    library_id=args.library_id,
                    snapshot_id=snapshot_id,
                    symbol_name=unit.symbol_name,
                    path=rel,
                    unit_type=unit.unit_type,
                    start_line=unit.start_line,
                    end_line=unit.end_line,
                )
                total_units += 1
            for edge in edges:
                conn.execute(
                    """
                    INSERT INTO code_rag.code_edges
                      (src_unit_id, dst_unit_id, library_id, relation, source, confidence)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        unit_ids.get(edge.src_unit_id, edge.src_unit_id),
                        unit_ids.get(edge.dst_unit_id, edge.dst_unit_id),
                        args.library_id,
                        edge.relation,
                        edge.source,
                        edge.confidence,
                    ),
                )
                total_edges += 1
            if len(prepared) >= 100 and index % 100 == 0:
                print(f"progress files={index} units={total_units}", flush=True)
        conn.execute(
            "UPDATE code_rag.code_ingest_runs SET status='completed', files=%s, units=%s, "
            "finished_at=now() WHERE run_id=%s",
            (len(files), total_units, run),
        )
        conn.commit()
    print(
        f"CODE_RAG_INGEST_OK language={args.language} files={len(files)} "
        f"units={total_units} edges={total_edges} skipped={skipped} copied={copied} "
        f"secrets_skipped={secret_skipped} license={license_id or 'unknown'} snapshot={snapshot_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
