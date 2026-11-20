"""Build one Zoekt shard in staging, then atomically replace old shards."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import uuid
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--name", required=True, help="Zoekt repo/shard name")
    parser.add_argument("--index-dir", required=True)
    parser.add_argument("--image", default="scipal-zoekt:latest")
    parser.add_argument("--parallelism", type=int, default=4)
    parser.add_argument("--restart-container", default="")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    index_dir = Path(args.index_dir).resolve()
    if not repo.exists():
        raise SystemExit(f"repo not found: {repo}")
    index_dir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:8]
    staging = index_dir.parent / f".zoekt-staging-{token}"
    backup = index_dir.parent / f".zoekt-backup-{token}"
    staging.mkdir()
    backup.mkdir()
    try:
        command = [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "/usr/local/bin/zoekt-index",
            "-v",
            f"{repo}:/repos/{args.name}:ro",
            "-v",
            f"{staging}:/index",
            args.image,
            "-index",
            "/index",
            "-parallelism",
            str(args.parallelism),
            "/repos/" + args.name,
        ]
        result = subprocess.run(command)
        if result.returncode != 0:
            raise RuntimeError(f"zoekt-index rc={result.returncode}")
        new_shards = sorted(staging.glob("*.zoekt"))
        if not new_shards or any(shard.stat().st_size == 0 for shard in new_shards):
            raise RuntimeError("no non-empty shards produced")
        old_shards = sorted(index_dir.glob(f"{args.name}_*.zoekt"))
        for shard in old_shards:
            shutil.move(str(shard), backup / shard.name)
        try:
            for shard in new_shards:
                shutil.move(str(shard), index_dir / shard.name)
        except Exception:
            for shard in new_shards:
                if (index_dir / shard.name).exists():
                    (index_dir / shard.name).unlink()
            for shard in backup.glob("*.zoekt"):
                shutil.move(str(shard), index_dir / shard.name)
            raise
        if args.restart_container:
            subprocess.run(["docker", "restart", args.restart_container], check=True)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "name": args.name,
                    "new_shards": [shard.name for shard in new_shards],
                    "old_shards": [shard.name for shard in old_shards],
                    "index_dir": str(index_dir),
                },
                ensure_ascii=False,
            )
        )
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
