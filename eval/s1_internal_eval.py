"""S1.3: production evidence retrieval baseline over the internal 50-question set."""

from __future__ import annotations

import argparse
import json
import os
import math
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _ids(item: dict) -> set[str]:
    out: set[str] = set()
    for key in ("highlight", "matched_sentences"):
        for row in item.get(key) or []:
            if row.get("sentence_id"):
                out.add(row["sentence_id"])
    for para in item.get("paragraph_details") or []:
        for sentence_id in para.get("sentence_ids") or []:
            if sentence_id:
                out.add(sentence_id)
    return out


def _anchor_ids(item: dict) -> set[str]:
    return {
        row["sentence_id"]
        for row in (item.get("highlight") or [])
        if row.get("sentence_id")
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", default=str(ROOT / "eval" / "s1_internal_questions.jsonl"))
    parser.add_argument("--output", default=str(ROOT / "eval" / "results" / "s1_internal_evidence.json"))
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--split", choices=("", "dev", "held_out"), default="")
    args = parser.parse_args()

    import api_server

    client = api_server.app.test_client()
    password = os.environ.get("SCIPAL_UI_ADMIN_PASSWORD", "").strip()
    if not password:
        raise SystemExit("SCIPAL_UI_ADMIN_PASSWORD is required")
    login = client.post(
        "/api/auth/login",
        json={"username": "ui_admin", "password": password},
    )
    if login.status_code != 200:
        raise SystemExit(f"login failed: {login.status_code}")

    questions = [
        json.loads(line)
        for line in Path(args.questions).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.limit:
        questions = questions[: args.limit]
    if args.split:
        split = json.loads((ROOT / "eval" / "s1_split.json").read_text(encoding="utf-8"))
        keep = set(split[args.split])
        questions = [row for row in questions if row["question_id"] in keep]

    rows = []
    recall10 = recall20 = anchor10 = 0
    mrr_sum = ndcg10_sum = 0.0
    started = time.time()
    for index, item in enumerate(questions, start=1):
        expected = set(item["gold_sentence_ids"]) | set(
            item.get("acceptable_sentence_ids") or []
        )
        t0 = time.time()
        response = client.post(
            "/api/evidence/search",
            json={"query": item["question"], "top_k": args.top_k},
        )
        if response.status_code != 200:
            raise SystemExit(f"{item['question_id']} HTTP {response.status_code}: {response.text[:300]}")
        payload = response.get_json() or {}
        evidence = payload.get("evidence") or []
        ranks = []
        anchor_rank = None
        for rank, row in enumerate(evidence, start=1):
            ids = _ids(row)
            if expected & ids:
                ranks.append(rank)
                if rank == 1 or anchor_rank is None:
                    pass
            if anchor_rank is None and expected & _anchor_ids(row):
                anchor_rank = rank
        hit10 = any(rank <= 10 for rank in ranks)
        hit20 = any(rank <= 20 for rank in ranks)
        anchor_hit10 = bool(anchor_rank and anchor_rank <= 10)
        recall10 += int(hit10)
        recall20 += int(hit20)
        anchor10 += int(anchor_hit10)
        if ranks:
            mrr_sum += 1.0 / min(ranks)
        # binary nDCG@10 on evidence item ranks
        dcg = sum(1.0 / math.log2(rank + 1) for rank in ranks if rank <= 10)
        ndcg10_sum += dcg
        rows.append(
            {
                "question_id": item["question_id"],
                "category": item["category"],
                "question": item["question"],
                "gold_paper_id": item["gold_paper_id"],
                "gold_sentence_ids": sorted(expected),
                "returned": len(evidence),
                "hit_ranks": ranks,
                "anchor_hit_rank": anchor_rank,
                "recall@10": hit10,
                "recall@20": hit20,
                "latency_s": round(time.time() - t0, 3),
                "sufficient": payload.get("sufficient"),
            }
        )
        if index % 5 == 0:
            print(f"progress {index}/{len(questions)}", flush=True)

    n = len(rows)
    summary = {
        "questions": n,
        "evidence_recall@10": round(recall10 / n, 4) if n else 0.0,
        "evidence_recall@20": round(recall20 / n, 4) if n else 0.0,
        "anchor_recall@10": round(anchor10 / n, 4) if n else 0.0,
        "mrr": round(mrr_sum / n, 4) if n else 0.0,
        "ndcg@10": round(ndcg10_sum / n, 4) if n else 0.0,
        "elapsed_s": round(time.time() - started, 1),
        "backend": "sentence (SCIPAL_EVIDENCE_BACKEND default)",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
