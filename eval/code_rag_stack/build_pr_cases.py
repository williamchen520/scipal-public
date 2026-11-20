"""Build real-query cases from GitHub PR titles + changed code files."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.request
from pathlib import Path

import psycopg

REPOS = {
    "lib_2c5709b07c77": "scverse/scanpy",
    "lib_anndata": "scverse/anndata",
    "lib_squidpy": "scverse/squidpy",
    "lib_scvi_tools": "scverse/scvi-tools",
    "lib_snakemake": "snakemake/snakemake",
    "lib_ggplot2": "tidyverse/ggplot2",
    "lib_dplyr": "tidyverse/dplyr",
    "lib_12473817b941": "nf-core/rnaseq",
    "lib_nfcore_scrnaseq": "nf-core/scrnaseq",
    "lib_nfcore_atacseq": "nf-core/atacseq",
}
SKIP = re.compile(
    r"^(docs?|chore|ci|build|release|merge|backport|bump|dependabot|version)\b",
    re.I,
)
CODE_SUFFIX = (".py", ".r", ".nf")


def clean_body(body: str) -> str:
    body = re.sub(r"<!--.*?-->", " ", body or "", flags=re.S)
    body = re.sub(r"```.*?```", " ", body, flags=re.S)
    body = re.sub(r"!\[[^]]*\]\([^)]*\)", " ", body)
    body = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", body)
    candidates = []
    for index, paragraph in enumerate(re.split(r"\n\s*\n", body)):
        text = re.sub(r"\s+", " ", paragraph).strip(" #*-\t")
        lower = text.lower()
        if len(text) < 30 or len(text) > 300:
            continue
        if lower.startswith(("[x]", "[ ]", "checklist", "fixes #", "closes #", "close http")):
            continue
        if any(
            phrase in lower
            for phrase in ("i used ai", "ai assistance", "hey there", "addresses the review", "template update")
        ):
            continue
        score = 0
        if "`" in text:
            score += 2
        if any(word in lower for word in ("function", "method", "class", "module", "pipeline", "fix", "add", "error", "data")):
            score += 1
        if "http" in lower:
            score -= 1
        candidates.append((score, -index, text))
    if not candidates:
        return ""
    return max(candidates)[2]

def api(url: str) -> list:
    token = os.environ.get("GH_TOKEN", "")
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "User-Agent": "SciPal"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="eval/code_rag_stack/pr_real_20.json")
    parser.add_argument("--per-library", type=int, default=2)
    parser.add_argument("--query-field", choices=["title", "body"], default="title")
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_CODE_READ_DSN", ""))
    args = parser.parse_args()
    if not os.environ.get("GH_TOKEN"):
        raise SystemExit("GH_TOKEN is required for PR mining")
    if not args.dsn:
        raise SystemExit("SCIPAL_CODE_READ_DSN is required")
    cases = []
    with psycopg.connect(args.dsn) as conn:
        for library_id, repo in REPOS.items():
            paths = {
                row[0]
                for row in conn.execute(
                    "SELECT f.path FROM code_rag.code_files f "
                    "JOIN code_rag.code_snapshots s ON s.snapshot_id=f.snapshot_id AND s.is_active "
                    "WHERE f.library_id=%s",
                    (library_id,),
                ).fetchall()
            }
            selected = 0
            pulls = api(
                f"https://api.github.com/repos/{repo}/pulls?state=closed&per_page=60"
                "&sort=created&direction=desc"
            )
            for pull in pulls:
                title = re.sub(r"\s*\(#\d+\)\s*$", "", pull.get("title", "")).strip()
                if len(title) < 12 or SKIP.search(title):
                    continue
                query = title
                if args.query_field == "body":
                    query = clean_body(pull.get("body", "") or "")
                    if not query:
                        continue
                try:
                    files = api(
                        f"https://api.github.com/repos/{repo}/pulls/{pull['number']}/files"
                        "?per_page=100"
                    )
                except Exception:
                    time.sleep(1)
                    continue
                targets = []
                for item in files:
                    filename = item.get("filename", "")
                    if not filename.lower().endswith(CODE_SUFFIX):
                        continue
                    filename = filename.replace("\\", "/")
                    if filename in paths and not filename.startswith(("tests/", "test/", "docs/")):
                        targets.append(filename)
                if not targets:
                    continue
                target = targets[0]
                cases.append(
                    {
                        "id": f"{library_id.replace('lib_', '')}_{selected + 1:02d}",
                        "library_id": library_id,
                        "category": "pr-title",
                        "query": query,
                        "expected_path": target,
                        "expected_paths": targets,
                        "expected_symbol": "",
                        "repo": repo,
                        "pr": pull["number"],
                    }
                )
                selected += 1
                if selected >= args.per_library:
                    break
            print(library_id, selected)
            time.sleep(0.2)
    Path(args.output).write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"WROTE {args.output} cases={len(cases)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
