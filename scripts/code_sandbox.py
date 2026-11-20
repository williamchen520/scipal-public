#!/usr/bin/env python3
"""Run an approved implementation proposal in a disposable Docker sandbox.

The sandbox has no network, a read-only workspace, resource limits and a
non-root user. It is a local trusted-user tool, not a public execution API.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(ROOT))

from code_rag.implement import validate_files


def docker_command(workdir: Path, image: str, test_module: str, timeout: int) -> tuple[list[str], str]:
    name = f"scipal-sandbox-{uuid.uuid4().hex[:10]}"
    command = [
        "docker", "run", "--rm",
        "--name", name,
        "--network", "none",
        "--memory", "512m",
        "--cpus", "0.5",
        "--pids-limit", "128",
        "--read-only",
        "--tmpfs", "/tmp:rw,size=64m",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--user", "65534:65534",
        "--entrypoint", "python",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-e", f"SCIPAL_SANDBOX_TIMEOUT={timeout}",
        "-v", f"{workdir.resolve()}:/workspace:ro",
        "-w", "/workspace",
        image,
        "-m", "unittest", "-v", test_module,
    ]
    return command, name


def run_sandbox(proposal: Path, *, image: str, test_module: str, timeout: int) -> dict:
    data = json.loads(proposal.read_text(encoding="utf-8-sig"))
    files = data.get("files") or []
    errors = validate_files(files)
    if errors:
        return {"status": "rejected", "errors": errors}
    workdir = Path(tempfile.mkdtemp(prefix="scipal-sandbox-"))
    try:
        for item in files:
            target = workdir / item["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(item["content"], encoding="utf-8")
        for path in [workdir, *workdir.rglob("*")]:
            try:
                path.chmod(0o755 if path.is_dir() else 0o644)
            except OSError:
                pass
        command, name = docker_command(workdir, image, test_module, timeout)
        started = time.perf_counter()
        try:
            process = subprocess.run(
                command, capture_output=True, text=True, timeout=timeout, check=False
            )
            elapsed = round(time.perf_counter() - started, 2)
            return {
                "status": "passed" if process.returncode == 0 else "failed",
                "exit_code": process.returncode,
                "duration_seconds": elapsed,
                "stdout": process.stdout[-8000:],
                "stderr": process.stderr[-8000:],
                "test_module": test_module,
                "image": image,
                "network": "none",
                "workspace": "read-only",
            }
        except subprocess.TimeoutExpired as exc:
            subprocess.run(["docker", "kill", name], capture_output=True, check=False)
            return {
                "status": "timeout",
                "exit_code": None,
                "duration_seconds": timeout,
                "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
                "stderr": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
                "test_module": test_module,
                "image": image,
            }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal", required=True)
    parser.add_argument("--image", default="scipal-app:latest")
    parser.add_argument("--test-module", default="test_proposal")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run_sandbox(
        Path(args.proposal), image=args.image, test_module=args.test_module, timeout=args.timeout
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"status={result['status']} exit={result.get('exit_code')} duration={result.get('duration_seconds')}")
        print(result.get("stdout", ""))
        if result.get("stderr"):
            print(result["stderr"])
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
