#!/usr/bin/env python3
"""Append-only deploy/rollback event ledger and rollback metrics."""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / "logs/deploy-events.jsonl"
ACTIONS = {"deploy", "rollback"}


def record(*, env: str, action: str, version: str = "", note: str = "",
           path: Path = DEFAULT, timestamp: str = "") -> dict:
    if action not in ACTIONS:
        raise ValueError(f"invalid action: {action}")
    event = {
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "env": env,
        "action": action,
        "version": version,
        "note": note,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def read_events(path: Path = DEFAULT) -> list[dict]:
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return sorted(events, key=lambda item: item.get("timestamp", ""))


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((p / 100) * (len(ordered) - 1)))))
    return ordered[index]


def rollback_metrics(events: list[dict]) -> dict:
    by_env: dict[str, list[dict]] = {}
    for event in events:
        by_env.setdefault(str(event.get("env") or ""), []).append(event)
    durations = []
    deployments = 0
    rollbacks = 0
    unmatched = 0
    for env_events in by_env.values():
        pending_deploy: datetime | None = None
        for event in sorted(env_events, key=lambda item: item.get("timestamp", "")):
            stamp = datetime.fromisoformat(str(event["timestamp"]).replace("Z", "+00:00"))
            if event.get("action") == "deploy":
                deployments += 1
                pending_deploy = stamp
            elif event.get("action") == "rollback":
                rollbacks += 1
                if pending_deploy:
                    durations.append((stamp - pending_deploy).total_seconds() / 3600)
                    pending_deploy = None
                else:
                    unmatched += 1
    return {
        "deployments": deployments,
        "rollbacks": rollbacks,
        "unmatched_rollbacks": unmatched,
        "median_rollback_hours": round(statistics.median(durations), 3) if durations else None,
        "p90_rollback_hours": round(_percentile(durations, 90), 3) if durations else None,
        "note": "event-ledger based; no events means null, not zero",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["record", "list", "metrics"])
    parser.add_argument("--env", default="")
    parser.add_argument("--event", default="deploy")
    parser.add_argument("--version", default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--path", default=str(DEFAULT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    path = Path(args.path)
    if args.action == "record":
        if not args.env:
            parser.error("record requires --env")
        event = record(env=args.env, action=args.event, version=args.version,
                       note=args.note, path=path)
        print(json.dumps(event, ensure_ascii=False))
        return 0
    events = read_events(path)
    if args.action == "list":
        for event in events:
            print(json.dumps(event, ensure_ascii=False))
        return 0
    result = rollback_metrics(events)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
