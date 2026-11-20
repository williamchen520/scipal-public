"""Onboard code repositories: ingest -> resolve -> BM25 sync."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

LANGUAGES = {"python", "r", "rmd", "nextflow", "javascript", "typescript", "auto"}


def load_manifest(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    repos = data.get("repos") if isinstance(data, dict) else data
    if not isinstance(repos, list) or not repos:
        raise ValueError("manifest must contain a non-empty repos list")
    return repos


def validate(repo: dict) -> list[str]:
    errors = []
    for field in ("library_id", "path", "repo_url", "language"):
        if not str(repo.get(field) or "").strip():
            errors.append(f"missing:{field}")
    if repo.get("language") not in LANGUAGES:
        errors.append(f"invalid:language:{repo.get('language')}")
    if repo.get("path") and not Path(str(repo["path"])).exists():
        errors.append(f"missing:path:{repo['path']}")
    return errors


def display(command: list[str]) -> str:
    return " ".join(re.sub(r"://[^/@]+@", "://***:***@", part) for part in command)


def commands(repo: dict, *, full: bool, dsn: str, bm25_dsn: str) -> list[list[str]]:
    base = [
        sys.executable,
        "-m",
        "code_rag.ingest",
        "--repo",
        str(repo["path"]),
        "--library-id",
        str(repo["library_id"]),
        "--repo-url",
        str(repo["repo_url"]),
        "--language",
        str(repo["language"]),
        "--dsn",
        dsn,
    ]
    if full:
        base.append("--full")
    return [
        base,
        [
            sys.executable,
            "-m",
            "code_rag.resolve",
            "--library-id",
            str(repo["library_id"]),
            "--dsn",
            dsn,
        ],
        [
            sys.executable,
            "-m",
            "code_rag.bm25",
            "--library-id",
            str(repo["library_id"]),
            "--code-dsn",
            dsn,
            "--bm25-dsn",
            bm25_dsn,
        ],
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="code_rag/onboarding.example.json")
    parser.add_argument("--library-id", action="append", default=[])
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_CODE_DSN", ""))
    parser.add_argument("--bm25-dsn", default=os.environ.get("SCIPAL_CODE_BM25_DSN", ""))
    args = parser.parse_args()
    repos = load_manifest(Path(args.manifest))
    if args.library_id:
        wanted = set(args.library_id)
        repos = [repo for repo in repos if repo.get("library_id") in wanted]
    if not repos:
        raise SystemExit("no matching repos")

    failed = False
    for repo in repos:
        errors = validate(repo)
        if errors:
            print(f"ONBOARD_INVALID {repo.get('library_id', '?')} {','.join(errors)}")
            failed = True
            break
        if not args.dsn or not args.bm25_dsn:
            raise SystemExit("SCIPAL_CODE_DSN and SCIPAL_CODE_BM25_DSN are required")
        for command in commands(repo, full=args.full, dsn=args.dsn, bm25_dsn=args.bm25_dsn):
            print("RUN " + display(command), flush=True)
            if args.apply:
                result = subprocess.run(command, env=os.environ.copy())
                if result.returncode != 0:
                    print(f"ONBOARD_FAILED {repo['library_id']} rc={result.returncode}")
                    return result.returncode
        print(f"ONBOARD_OK {repo['library_id']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
