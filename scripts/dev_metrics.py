#!/usr/bin/env python3
"""Collect development metrics without inventing missing data.

PR metrics use GitHub API when a token is available; otherwise local git only.
Failure/rollback metrics are label-based, not deploy telemetry.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((p / 100) * (len(ordered) - 1)))))
    return ordered[index]


def summarize_prs(prs: list[dict]) -> dict:
    sized = [pr for pr in prs if "additions" in pr and "deletions" in pr]
    sizes = [int(pr["additions"]) + int(pr["deletions"]) for pr in sized]
    lead_hours = []
    for pr in prs:
        if not pr.get("merged_at") or not pr.get("created_at"):
            continue
        created = datetime.fromisoformat(pr["created_at"].replace("Z", "+00:00"))
        merged = datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00"))
        lead_hours.append((merged - created).total_seconds() / 3600)
    failures = 0
    for pr in prs:
        labels = {str(item.get("name", "")).lower() for item in pr.get("labels") or []}
        if labels & {"incident", "rollback", "revert", "failed"}:
            failures += 1
    return {
        "merged_prs": len(prs),
        "size_sample": len(sizes),
        "median_pr_size": statistics.median(sizes) if sizes else None,
        "p90_pr_size": percentile(sizes, 90),
        "median_lead_time_hours": round(statistics.median(lead_hours), 2) if lead_hours else None,
        "p90_lead_time_hours": round(percentile(lead_hours, 90), 2) if lead_hours else None,
        "failure_prs": failures,
        "change_failure_rate": round(failures / len(prs), 4) if prs else None,
        "failure_metric": "label-based (incident/rollback/revert/failed); not deploy telemetry",
    }


def fetch_prs(repo: str, token: str, since: datetime) -> list[dict]:
    result = []
    page = 1
    while page <= 10:
        query = urllib.parse.urlencode({"state": "closed", "per_page": 100, "page": page,
                                        "sort": "updated", "direction": "desc"})
        request = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/pulls?{query}",
            headers={"Authorization": f"Bearer {token}", "User-Agent": "SciPal"},
        )
        data = json.loads(urllib.request.urlopen(request, timeout=30).read())
        if not data:
            break
        page_has_recent = False
        for pr in data:
            merged = pr.get("merged_at")
            if merged and datetime.fromisoformat(merged.replace("Z", "+00:00")) >= since:
                result.append(pr)
                page_has_recent = True
        if not page_has_recent:
            break
        page += 1
    return result


def hydrate_sizes(prs: list[dict], repo: str, token: str, limit: int) -> None:
    for pr in prs[:limit]:
        request = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/pulls/{pr['number']}",
            headers={"Authorization": f"Bearer {token}", "User-Agent": "SciPal"},
        )
        try:
            detail = json.loads(urllib.request.urlopen(request, timeout=15).read())
            pr["additions"] = detail.get("additions")
            pr["deletions"] = detail.get("deletions")
        except Exception:
            continue


def local_metrics(since_days: int) -> dict:
    raw = subprocess.run(
        ["git", "rev-list", "--count", f"--since={since_days} days ago", "HEAD"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    ).stdout.strip()
    return {"commits": int(raw) if raw.isdigit() else None}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="williamchen520/sci-pal")
    parser.add_argument("--since-days", type=int, default=30)
    parser.add_argument("--test-duration", type=float, default=None)
    parser.add_argument("--sample-size", type=int, default=30)
    parser.add_argument("--test-duration-file", default="")
    parser.add_argument("--events", default="logs/deploy-events.jsonl")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    since = datetime.now(timezone.utc) - timedelta(days=args.since_days)
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    result = {"window_days": args.since_days, "local": local_metrics(args.since_days)}
    if token:
        prs = fetch_prs(args.repo, token, since)
        hydrate_sizes(prs, args.repo, token, max(1, args.sample_size))
        result["github"] = summarize_prs(prs)
    else:
        result["github"] = None
        result["note"] = "GH_TOKEN/GITHUB_TOKEN missing; PR metrics not collected"
    duration = args.test_duration
    duration_source = "argument" if duration is not None else None
    if duration is None and args.test_duration_file:
        duration_path = Path(args.test_duration_file)
        if duration_path.exists():
            payload = json.loads(duration_path.read_text(encoding="utf-8"))
            duration = payload.get("duration_seconds")
            duration_source = str(duration_path)
    result["test_duration_seconds"] = duration
    result["test_duration_source"] = duration_source
    if duration is None:
        result["test_duration_note"] = "run scripts/run_tests.py and pass --test-duration-file; not inferred"
    from scripts.deploy_events import read_events, rollback_metrics
    rollback = rollback_metrics(read_events(Path(args.events)))
    result["rollback"] = rollback
    result["rollback_time_hours"] = rollback["median_rollback_hours"]
    result["rollback_note"] = rollback["note"]
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"window_days={args.since_days} commits={result['local'].get('commits')}")
        if result["github"]:
            for key, value in result["github"].items():
                print(f"{key}={value}")
        else:
            print(result.get("note"))
        print(f"test_duration_seconds={duration}")
        print(f"rollback_time_hours={result['rollback_time_hours']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
