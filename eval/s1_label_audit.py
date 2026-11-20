"""S1 label/gold alignment audit: capture gold text and miss evidence."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", default=str(ROOT / "eval" / "s1_internal_questions.jsonl"))
    parser.add_argument("--result", default=str(ROOT / "eval" / "results" / "s1_internal_evidence.json"))
    parser.add_argument("--output", default=str(ROOT / "eval" / "results" / "s1_label_audit_raw.json"))
    args = parser.parse_args()

    import psycopg
    from psycopg.rows import dict_row

    import api_server
    from services.db.pg_pool import corpus_connection

    questions = [
        json.loads(line)
        for line in Path(args.questions).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    result = json.loads(Path(args.result).read_text(encoding="utf-8"))
    hits = {row["question_id"]: row for row in result["rows"]}
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

    conn = corpus_connection()
    rows = []
    try:
        for question in questions:
            sentence_id = question["gold_sentence_ids"][0]
            gold = conn.execute(
                "SELECT s.sentence_id, s.text AS sentence_text, s.para_id, "
                "p.text AS para_text, p.paper_id, pp.title AS paper_title "
                "FROM sentences s JOIN paragraphs p ON p.para_id=s.para_id "
                "JOIN papers pp ON pp.paper_id=s.paper_id WHERE s.sentence_id=%s",
                (sentence_id,),
            ).fetchone()
            if not gold:
                continue
            hit = hits.get(question["question_id"], {})
            returned = []
            if not hit.get("recall@10"):
                response = client.post(
                    "/api/evidence/search",
                    json={"query": question["question"], "top_k": 20},
                )
                payload = response.get_json() or {}
                for item in (payload.get("evidence") or [])[:10]:
                    for row in item.get("highlight") or []:
                        returned.append(
                            {
                                "sentence_id": row.get("sentence_id"),
                                "text": row.get("text"),
                                "paper_id": item.get("paper_id"),
                            }
                        )
            rows.append(
                {
                    "question_id": question["question_id"],
                    "category": question["category"],
                    "question": question["question"],
                    "gold_paper_id": question["gold_paper_id"],
                    "paper_title": gold["paper_title"],
                    "gold_sentence_id": sentence_id,
                    "gold_sentence": gold["sentence_text"],
                    "gold_para_id": gold["para_id"],
                    "gold_para": (gold["para_text"] or "")[:2000],
                    "hit": bool(hit.get("recall@10")),
                    "returned_evidence": returned,
                }
            )
    finally:
        conn.close()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"rows={len(rows)} misses={len(misses)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
