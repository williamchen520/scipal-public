"""Sync managed repos from Git, with snapshot/shard rollback."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from code_rag.bm25 import sync_library


def git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def active_snapshot(dsn: str, library_id: str) -> tuple[str, str]:
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            "SELECT snapshot_id,commit_sha FROM code_rag.code_snapshots "
            "WHERE library_id=%s AND is_active LIMIT 1",
            (library_id,),
        ).fetchone()
    return (row[0], row[1]) if row else ("", "")


def set_active(dsn: str, library_id: str, snapshot_id: str) -> None:
    with psycopg.connect(dsn) as conn:
        conn.execute("UPDATE code_rag.code_snapshots SET is_active=false WHERE library_id=%s", (library_id,))
        if snapshot_id:
            conn.execute(
                "UPDATE code_rag.code_snapshots SET is_active=true WHERE library_id=%s AND snapshot_id=%s",
                (library_id, snapshot_id),
            )
        conn.commit()


def backup_shards(index_dir: Path, name: str, token: str) -> Path:
    backup = index_dir.parent / f".sync-backup-{token}"
    backup.mkdir()
    for shard in index_dir.glob(f"{name}_*.zoekt"):
        shutil.copy2(shard, backup / shard.name)
    return backup


def restore_shards(index_dir: Path, name: str, backup: Path) -> None:
    for shard in index_dir.glob(f"{name}_*.zoekt"):
        shard.unlink()
    for shard in backup.glob("*.zoekt"):
        shutil.copy2(shard, index_dir / shard.name)


def run(command: list[str], dsn: str, bm25_dsn: str) -> None:
    env = os.environ.copy()
    env["SCIPAL_CODE_DSN"] = dsn
    env["SCIPAL_CODE_BM25_DSN"] = bm25_dsn
    result = subprocess.run(command, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"command failed rc={result.returncode}: {' '.join(command[:3])}")


def sync_repo(repo: dict, args, dsn: str, bm25_dsn: str) -> dict:
    path = Path(str(repo["path"]))
    library_id = str(repo["library_id"])
    name = str(repo.get("zoekt_name") or path.name)
    if not path.exists():
        return {"library_id": library_id, "status": "skip", "reason": "repo missing"}
    prev_snapshot, prev_commit = active_snapshot(dsn, library_id)
    if args.fetch:
        ref = str(repo.get("ref") or "HEAD")
        git(path, "fetch", "--depth", "1", "origin", ref)
        git(path, "checkout", "--detach", "FETCH_HEAD")
    commit = git(path, "rev-parse", "HEAD")
    if commit == prev_commit:
        return {"library_id": library_id, "status": "skip", "reason": "same commit", "commit": commit}
    if not args.apply:
        return {"library_id": library_id, "status": "would_sync", "commit": commit, "previous": prev_commit}
    token = uuid.uuid4().hex[:8]
    backup = backup_shards(Path(args.zoekt_index_dir), name, token) if not args.skip_zoekt else None
    try:
        run(
            [sys.executable, "-m", "code_rag.ingest", "--repo", str(path), "--library-id", library_id,
             "--repo-url", str(repo["repo_url"]), "--language", str(repo["language"]), "--dsn", dsn],
            dsn, bm25_dsn,
        )
        run([sys.executable, "-m", "code_rag.resolve", "--library-id", library_id, "--dsn", dsn], dsn, bm25_dsn)
        run([sys.executable, "-m", "code_rag.bm25", "--library-id", library_id, "--code-dsn", dsn,
             "--bm25-dsn", bm25_dsn], dsn, bm25_dsn)
        if not args.skip_zoekt:
            run(
                [sys.executable, "scripts/code_zoekt_sync.py", "--repo", str(path), "--name", name,
                 "--index-dir", args.zoekt_index_dir, "--restart-container", args.restart_container],
                dsn, bm25_dsn,
            )
        run(
            [sys.executable, "scripts/code_health.py", "--library-id", library_id,
             "--code-dsn", dsn, "--bm25-dsn", bm25_dsn],
            dsn, bm25_dsn,
        )
        return {"library_id": library_id, "status": "ok", "commit": commit, "previous": prev_commit}
    except Exception:
        set_active(dsn, library_id, prev_snapshot)
        if prev_snapshot:
            try:
                sync_library(
                    code_dsn=dsn,
                    library_id=library_id,
                    snapshot_id=prev_snapshot,
                    bm25_dsn=bm25_dsn,
                )
            except Exception as rollback_error:  # noqa: BLE001
                print(f"BM25_ROLLBACK_ERROR {rollback_error}", flush=True)
        if backup is not None:
            restore_shards(Path(args.zoekt_index_dir), name, backup)
            if args.restart_container:
                subprocess.run(["docker", "restart", args.restart_container], check=False)
        raise
    finally:
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="code_rag/onboarding.example.json")
    parser.add_argument("--code-dsn", default=os.environ.get("SCIPAL_CODE_DSN", ""))
    parser.add_argument("--bm25-dsn", default=os.environ.get("SCIPAL_CODE_BM25_DSN", ""))
    parser.add_argument("--zoekt-index-dir", default=os.environ.get("SCIPAL_ZOekt_INDEX_DIR", "G:/tools/zoekt/index"))
    parser.add_argument("--restart-container", default="deploy-zoekt-1")
    parser.add_argument("--skip-zoekt", action="store_true")
    parser.add_argument("--no-fetch", dest="fetch", action="store_false")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--loop", type=int, default=0, help="seconds; 0 runs once")
    parser.add_argument("--library-id", action="append", default=[])
    args = parser.parse_args()
    if not args.code_dsn or not args.bm25_dsn:
        raise SystemExit("SCIPAL_CODE_DSN and SCIPAL_CODE_BM25_DSN are required")
    data = json.loads(Path(args.manifest).read_text(encoding="utf-8-sig"))
    repos = data.get("repos") if isinstance(data, dict) else data
    if args.library_id:
        wanted = set(args.library_id)
        repos = [repo for repo in repos if repo.get("library_id") in wanted]
    while True:
        for repo in repos:
            try:
                print(json.dumps(sync_repo(repo, args, args.code_dsn, args.bm25_dsn), ensure_ascii=False))
            except Exception as exc:  # noqa: BLE001
                print(json.dumps({"library_id": repo.get("library_id"), "status": "failed", "error": str(exc)}, ensure_ascii=False))
                return 1
        if not args.loop:
            break
        time.sleep(max(30, args.loop))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
