#!/usr/bin/env python3
"""Local sandbox worker: the only process with Docker socket access.

Run on the host, bind to a private interface, protect with a token.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.code_sandbox import run_sandbox

TOKEN = os.environ.get("SCIPAL_SANDBOX_TOKEN", "").strip()
SEMAPHORE = threading.Semaphore(1)
QUEUE_WAIT = max(0, int(os.environ.get("SCIPAL_SANDBOX_QUEUE_WAIT", "30")))
EVENTS = Path(os.environ.get("SCIPAL_SANDBOX_EVENTS", "logs/sandbox-events.jsonl"))


class Handler(BaseHTTPRequestHandler):
    server_version = "SciPalSandbox/1"

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            acquired = SEMAPHORE.acquire(blocking=False)
            if acquired:
                SEMAPHORE.release()
            self._json(200, {"ok": True, "busy": not acquired})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/execute":
            self._json(404, {"error": "not found"})
            return
        if TOKEN and self.headers.get("X-SCIPAL-Sandbox-Token", "") != TOKEN:
            self._json(403, {"error": "forbidden"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            proposal = body.get("proposal")
            if not isinstance(proposal, dict):
                self._json(400, {"error": "proposal must be an object"})
                return
            test_module = str(body.get("test_module") or "")
            if not test_module.replace("_", "").replace(".", "").isalnum():
                self._json(400, {"error": "invalid test_module"})
                return
            timeout = max(1, min(int(body.get("timeout") or 60), 60))
            if not SEMAPHORE.acquire(timeout=QUEUE_WAIT):
                self._json(429, {"error": "sandbox busy", "queue_wait_seconds": QUEUE_WAIT})
                return
            try:
                with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
                    json.dump(proposal, handle, ensure_ascii=False)
                    path = Path(handle.name)
                try:
                    result = run_sandbox(
                        path,
                        image=str(body.get("image") or "scipal-app:latest"),
                        test_module=test_module,
                        timeout=timeout,
                    )
                finally:
                    path.unlink(missing_ok=True)
            finally:
                SEMAPHORE.release()
            EVENTS.parent.mkdir(parents=True, exist_ok=True)
            with EVENTS.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": result.get("status"),
                    "exit_code": result.get("exit_code"),
                    "duration_seconds": result.get("duration_seconds"),
                    "test_module": result.get("test_module"),
                    "image": result.get("image"),
                }, ensure_ascii=False) + "\n")
            self._json(200, result)
        except Exception as exc:  # noqa: BLE001
            self._json(500, {"error": str(exc)[:500]})

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5020)
    args = parser.parse_args()
    if not TOKEN:
        raise SystemExit("SCIPAL_SANDBOX_TOKEN is required")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"SANDBOX_WORKER {args.host}:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
