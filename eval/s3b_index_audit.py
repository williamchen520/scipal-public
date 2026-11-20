"""S3.B: data/index quality audit for the internal question set."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    import os

    from services.db.pg_pool import corpus_connection
    from services.search.sentence_hybrid import _ts_query

    questions = [
        json.loads(line)
        for line in (ROOT / "eval" / "s1_internal_questions.v1.1.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    result = {
        row["question_id"]: row
        for row in json.loads(
            (ROOT / "eval" / "results" / "s1_v1.1_evidence.json").read_text(encoding="utf-8")
        )["rows"]
    }
    conn = corpus_connection()
    rows = []
    try:
        for question in questions:
            sentence_id = question["gold_sentence_ids"][0]
            gold = conn.execute(
                "SELECT s.sentence_id, s.text, s.search_vector, "
                "p.section_level1, p.section_level2, p.paper_id, "
                "pp.duplicate_of, pp.title "
                "FROM sentences s JOIN paragraphs p ON p.para_id=s.para_id "
                "JOIN papers pp ON pp.paper_id=s.paper_id WHERE s.sentence_id=%s",
                (sentence_id,),
            ).fetchone()
            if not gold:
                continue
            ts_query = _ts_query(question["question"])
            fts_match = False
            rank = 0.0
            if ts_query:
                hit = conn.execute(
                    "SELECT ts_rank(search_vector, to_tsquery('english', %s)) AS rank "
                    "FROM sentences WHERE sentence_id=%s AND search_vector @@ "
                    "to_tsquery('english', %s)",
                    (ts_query, sentence_id, ts_query),
                ).fetchone()
                if hit:
                    fts_match = True
                    rank = float(hit["rank"] or 0.0)
            lexemes = conn.execute(
                "SELECT array_length(tsvector_to_array(search_vector), 1) AS n "
                "FROM sentences WHERE sentence_id=%s",
                (sentence_id,),
            ).fetchone()
            rows.append(
                {
                    "question_id": question["question_id"],
                    "category": question["category"],
                    "hit": bool(result.get(question["question_id"], {}).get("recall@10")),
                    "gold_sentence_id": sentence_id,
                    "sentence_chars": len(gold["text"] or ""),
                    "section_l1": gold["section_level1"],
                    "section_l2": gold["section_level2"],
                    "section_missing": not (gold["section_level1"] or gold["section_level2"]),
                    "duplicate_of": gold["duplicate_of"],
                    "fts_match": fts_match,
                    "fts_rank": round(rank, 6),
                    "lexeme_count": lexemes["n"] if lexemes else 0,
                    "query_terms": ts_query,
                }
            )
    finally:
        conn.close()

    misses = [row for row in rows if not row["hit"]]
    summary = {
        "questions": len(rows),
        "hits": sum(row["hit"] for row in rows),
        "misses": len(misses),
        "gold_fts_match": sum(row["fts_match"] for row in rows),
        "miss_fts_match": sum(row["fts_match"] for row in misses),
        "miss_no_fts_match": sum(not row["fts_match"] for row in misses),
        "miss_section_missing": sum(row["section_missing"] for row in misses),
        "gold_section_missing": sum(row["section_missing"] for row in rows),
        "miss_by_category": dict(Counter(row["category"] for row in misses)),
        "miss_ids_no_fts": [row["question_id"] for row in misses if not row["fts_match"]],
        "miss_ids_fts": [row["question_id"] for row in misses if row["fts_match"]],
    }
    out = ROOT / "eval" / "results" / "s3b_index_audit.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
