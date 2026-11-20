"""S1.5: classify evidence retrieval misses for the internal set."""

from __future__ import annotations

import argparse
import json
import os

import psycopg
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _sentence_ids(item: dict) -> set[str]:
    out = set()
    for key in ("highlight", "matched_sentences"):
        for row in item.get(key) or []:
            if row.get("sentence_id"):
                out.add(row["sentence_id"])
    for para in item.get("paragraph_details") or []:
        for sentence_id in para.get("sentence_ids") or []:
            out.add(sentence_id)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", default=str(ROOT / "eval" / "s1_internal_questions.jsonl"))
    parser.add_argument("--result", default=str(ROOT / "eval" / "results" / "s1_internal_evidence.json"))
    parser.add_argument("--output", default=str(ROOT / "eval" / "results" / "s1_failure_taxonomy.json"))
    args = parser.parse_args()

    import api_server

    questions = {
        row["question_id"]: row
        for row in (
            json.loads(line)
            for line in Path(args.questions).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    result = json.loads(Path(args.result).read_text(encoding="utf-8"))
    misses = [row for row in result["rows"] if not row["recall@10"]]
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

    gold_paras = {}
    dsn = os.environ.get("SCIPAL_PG_OWNER_DSN", "").strip()
    if dsn:
        with psycopg.connect(dsn) as conn:
            for item in questions.values():
                for sentence_id in item["gold_sentence_ids"]:
                    row = conn.execute(
                        "SELECT para_id FROM sentences WHERE sentence_id=%s",
                        (sentence_id,),
                    ).fetchone()
                    if row:
                        gold_paras[sentence_id] = row[0]

    rows = []
    for miss in misses:
        question = questions[miss["question_id"]]
        response = client.post(
            "/api/evidence/search",
            json={"query": question["question"], "top_k": 20},
        )
        payload = response.get_json() or {}
        evidence = payload.get("evidence") or []
        paper_ids = {item.get("paper_id") for item in evidence if item.get("paper_id")}
        para_ids = {item.get("para_id") for item in evidence if item.get("para_id")}
        returned_sentences = set()
        for item in evidence:
            returned_sentences.update(_sentence_ids(item))
        gold = set(question["gold_sentence_ids"])
        gold_paper = question["gold_paper_id"]

        if gold_paper not in paper_ids:
            kind = "retrieval_miss"
        elif gold & returned_sentences:
            kind = "ranking_miss"
        elif any(
            gold_paras.get(sentence_id) in para_ids
            for sentence_id in question["gold_sentence_ids"]
        ):
            kind = "context_miss"
        elif gold_paper in paper_ids:
            kind = "paper_sentence_miss"
        else:
            kind = "unknown"

        rows.append(
            {
                "question_id": miss["question_id"],
                "category": miss["category"],
                "question": question["question"],
                "gold_paper_id": gold_paper,
                "gold_sentence_ids": sorted(gold),
                "hit_ranks": miss["hit_ranks"],
                "returned_papers": sorted(paper_ids),
                "returned_paras": sorted(para_ids),
                "classification": kind,
                "returned": len(evidence),
            }
        )

    by_category = defaultdict(Counter)
    for row in rows:
        by_category[row["category"]][row["classification"]] += 1
    summary = {
        "misses": len(rows),
        "total": result["summary"]["questions"],
        "by_classification": dict(Counter(row["classification"] for row in rows)),
        "by_category": {key: dict(value) for key, value in by_category.items()},
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
