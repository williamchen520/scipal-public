#!/usr/bin/env python3
"""Download pinned code repositories for CodeRAG (shallow, no submodules)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from code_rag.source_meta import detect_license


def run(args: list[str], cwd: Path | None = None) -> str:
    process = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if process.returncode != 0:
        raise RuntimeError(f"{' '.join(args)}: {process.stderr.strip()}")
    return process.stdout.strip()


def license_file(repo: Path) -> str:
    for name in ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING"):
        if (repo / name).is_file():
            return name
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="code_rag/repos.json")
    parser.add_argument("--root", default="")
    parser.add_argument("--only", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--lock", default="code_rag/repos.lock.json")
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    root = Path(args.root or manifest.get("root", "G:/repos/code_rag"))
    only = {item.strip() for item in args.only.split(",") if item.strip()}
    lock_path = Path(args.lock)
    lock = json.loads(lock_path.read_text(encoding="utf-8")) if lock_path.exists() else {"repos": {}}
    for repo in manifest["repos"]:
        repo_id = repo["id"]
        if only and repo_id not in only:
            continue
        url = repo["url"]
        if not url.startswith("https://github.com/"):
            raise SystemExit(f"unsupported repo url: {url}")
        target = Path(repo.get("path") or (root / repo_id))
        if target.exists() and (target / ".git").exists():
            commit = run(["git", "-C", str(target), "rev-parse", "HEAD"])
            print(f"SKIP {repo_id} {commit[:8]} {target}")
            lock["repos"][repo_id] = {**repo, "commit": commit, "path": str(target), "status": "present"}
            continue
        if args.dry_run:
            print(f"PLAN {repo_id} {url} ref={repo.get('ref')} -> {target}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        clone = ["git", "clone", "--depth", "1", "--no-recurse-submodules", "--single-branch"]
        ref = str(repo.get("ref") or "").strip()
        if ref and ref not in {"main", "master"}:
            clone += ["--branch", ref]
        clone += [url, str(target)]
        print(f"CLONE {repo_id} {url} ref={ref or 'default'}")
        run(clone)
        commit = run(["git", "-C", str(target), "rev-parse", "HEAD"])
        detected = detect_license(target)
        lock["repos"][repo_id] = {
            **repo,
            "commit": commit,
            "path": str(target),
            "detected_license": detected,
            "license_file": license_file(target),
            "status": "downloaded",
        }
        print(f"OK {repo_id} {commit[:8]} license={detected or 'UNKNOWN'}")
    lock_path.write_text(json.dumps(lock, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"LOCK {lock_path} repos={len(lock['repos'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
