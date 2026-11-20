"""Paper assignment and title/DOI recall helpers.

Extracted from review_generator; re-exported there for compatibility.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Optional

from . import title_recall
from .query_builder import build_section_query, is_paper_relevant, rank_papers


def assign_papers_to_outline(
    outline: dict,
    papers: list[dict],
    evidence_cards: Optional[list[dict]] = None,
) -> dict:
    """V26.1: 自动计算每篇论文与各章节的相似度，把论文发配到相关章节。

    简单版本：用关键词匹配计算相似度，把论文发配到最相关的章节。

    Args:
        outline: 大纲 JSON {"sections": [...]}
        papers: 论文列表 [{"paper_id": ..., "title": ..., ...}]
        evidence_cards: 证据卡片列表（可选，用于更精确的匹配）

    Returns:
        更新后的大纲（每章节包含 assigned_paper_ids）
    """
    if not outline or not outline.get("sections"):
        return outline

    if not papers:
        print("⚠️  assign_papers_to_outline: papers 列表为空！")
        return outline

    print(f"📋 assign_papers_to_outline: 开始分配 {len(papers)} 篇论文到 {len(outline['sections'])} 个章节")

    # 1. 收集每个章节的关键词
    section_keywords = {}
    for sec in outline["sections"]:
        sec_text = sec.get("title", "") + " " + sec.get("description", "")
        for para in sec.get("paragraphs", []):
            sec_text += " " + para.get("topic", "") + " " + para.get("description", "")
        # 简单分词（按空格和标点）
        keywords = set(sec_text.lower().split())
        section_keywords[sec["section_id"]] = keywords

    # 2. 为每篇论文计算与每个章节的相似度
    assignments = {}  # paper_id -> section_id
    section_ids = [sec["section_id"] for sec in outline["sections"]]
    round_robin_idx = 0  # V31.78: 轮询索引，用于平均分配没有匹配到的论文
    for paper in papers:
        pid = paper.get("paper_id", "")
        title = paper.get("title", "")
        if not pid:
            continue

        # 论文的关键词（标题简单分词）
        paper_keywords = set(title.lower().split())

        # 计算与每个章节的相似度（关键词重叠数）
        best_section = None
        best_score = 0
        for sec_id, sec_keywords in section_keywords.items():
            overlap = len(paper_keywords & sec_keywords)
            if overlap > best_score:
                best_score = overlap
                best_section = sec_id

        # V31.78: 如果没有匹配到任何章节（best_score=0），按轮询方式平均分配
        if best_section is None or best_score == 0:
            best_section = section_ids[round_robin_idx % len(section_ids)]
            round_robin_idx += 1

        assignments[pid] = best_section

    print(f"📊 分配统计：关键词匹配 {len(papers) - round_robin_idx} 篇，轮询分配 {round_robin_idx} 篇")

    # 3. 更新大纲的 assigned_paper_ids
    for sec in outline["sections"]:
        sec_id = sec["section_id"]
        sec_papers = [pid for pid, sid in assignments.items() if sid == sec_id]
        sec["assigned_paper_ids"] = sec_papers

        # 段落级分配：按段落关键词匹配
        for para in sec.get("paragraphs", []):
            para_text = para.get("topic", "") + " " + para.get("description", "")
            para_keywords = set(para_text.lower().split())

            para_papers = []
            for pid in sec_papers:
                paper = next((p for p in papers if p.get("paper_id") == pid), None)
                if not paper:
                    continue
                title = paper.get("title", "")
                paper_keywords = set(title.lower().split())
                overlap = len(paper_keywords & para_keywords)
                if overlap > 0:
                    para_papers.append(pid)

            para["assigned_paper_ids"] = para_papers

    return outline


# ──────────────────────────────────────────────
# V33.17: 摘要回退支持 —— 全文库 DOI 映射
# ──────────────────────────────────────────────

_FULLTEXT_DOI_MAP: Optional[dict[str, str]] = None
_PAPER_TITLE_CACHE: dict[str, str] = {}


def _research_db_path() -> Optional[Path]:
    # Kept for call-site compatibility; title recall now uses PostgreSQL.
    return Path(__file__).resolve().parent.parent.parent / "data" / "research.db"


def _title_recall_limits() -> tuple[int, int]:
    """(title-match candidates, extra papers per section), env-tunable."""
    import os

    limit = max(1, min(int(os.environ.get("SCIPAL_TITLE_RECALL_LIMIT", "10")), 20))
    max_add = max(0, min(int(os.environ.get("SCIPAL_TITLE_RECALL_MAX", "8")), 12))
    return limit, max_add


def _paper_titles(paper_ids: list[str]) -> dict[str, str]:
    """Titles for the candidate papers (module-level cache, PG-backed)."""
    missing = [pid for pid in paper_ids if pid not in _PAPER_TITLE_CACHE]
    if missing:
        try:
            from services.db.pg_pool import main_read_connection

            pg = main_read_connection()
            try:
                rows = pg.execute(
                    "SELECT paper_id, title FROM papers WHERE paper_id = ANY(%s)",
                    (missing,),
                ).fetchall()
            finally:
                pg.close()
            for row in rows:
                _PAPER_TITLE_CACHE[row["paper_id"]] = row["title"] or ""
        except Exception:
            pass
    return {pid: _PAPER_TITLE_CACHE.get(pid, "") for pid in paper_ids}


def _get_fulltext_doi_map() -> dict[str, str]:
    """DOI -> paper_id mapping from PostgreSQL (module-level cache)."""
    global _FULLTEXT_DOI_MAP
    if _FULLTEXT_DOI_MAP is None:
        doi_map: dict[str, str] = {}
        try:
            from services.db.pg_pool import main_read_connection

            pg = main_read_connection()
            try:
                rows = pg.execute(
                    "SELECT paper_id, doi FROM papers "
                    "WHERE doi IS NOT NULL AND btrim(doi) <> ''"
                ).fetchall()
            finally:
                pg.close()
            for row in rows:
                doi_map[row["doi"].strip().lower()] = row["paper_id"]
        except Exception as e:
            print(f"加载全文 DOI 映射失败: {e}")
        _FULLTEXT_DOI_MAP = doi_map
        print(f"全文库 DOI 映射已加载（{len(doi_map)} 篇）")
    return _FULLTEXT_DOI_MAP


def search_and_assign_papers(
    outline: dict,
    topic: str,
    max_papers: int = 100,
    retriever=None,
    should_cancel=None,
) -> tuple[dict, list[dict]]:
    """V31.79: 按大纲内容搜索论文，然后自动分配给对应的章节和段落。

    流程（按用户思路重写）：
    1. 遍历每个章节
    2. 按章节标题 + 段落主题搜索论文
    3. 每个章节取排名靠前的论文
    4. 总数不超过 max_papers
    5. 直接分配到对应的章节（不需要后面再分配）

    Args:
        outline: 大纲 JSON {"sections": [...]}
        topic: 综述主题
        max_papers: 最大论文数
        retriever: 检索器实例

    Returns:
        (更新后的大纲, 论文列表)
    """
    if not outline or not outline.get("sections"):
        return outline, []

    if retriever is None:
        return outline, []

    print(f"🔍 开始按大纲内容搜索论文和证据卡片...")

    # V32.4: 从综述主题提取核心关键词，加到每个章节的搜索关键词里
    # 这样搜索到的文献就会跟综述主题相关
    STOP_WORDS = {'in', 'from', 'to', 'the', 'of', 'and', 'or', 'a', 'an', 'for', 'with', 'on', 'at', 'by', 'as', 'into', 'via', 'per', 'vs', 'etc'}
    topic_keywords = []
    if topic:
        # 按空格和冒号分割
        words = topic.replace(':', ' ').replace('-', ' ').split()
        for w in words:
            w = w.strip().strip('(),.:;!?')
            if len(w) >= 3 and w.lower() not in STOP_WORDS:
                topic_keywords.append(w)
    print(f"📌 综述主题核心关键词: {topic_keywords}")

    sections = outline.get("sections", [])
    num_sections = len(sections)
    # 每个章节平均分配的论文数
    papers_per_section = max(1, max_papers // num_sections)
    print(f"📊 共 {num_sections} 个章节，每章节约 {papers_per_section} 篇论文，总数不超过 {max_papers}")

    all_papers = {}  # paper_id -> paper dict
    all_evidence_cards = {}  # evidence_id -> evidence card dict
    total_assigned = 0
    evidence_seq = 0  # 证据卡片序号

    # 1. 遍历每个章节，按章节关键词搜索
    for sec_idx, sec in enumerate(sections):
        if should_cancel is not None and should_cancel():
            from services.workflow.cancel import CancelledError

            raise CancelledError(f"cancelled before section {sec_idx + 1}")

        sec_id = sec.get("section_id", "")
        sec_title = sec.get("title", "").strip()

        # V32.1: 优先用章节和段落的 keywords 字段搜索；如果没有，就用标题和主题
        section_keywords = sec.get("keywords", [])
        if isinstance(section_keywords, str):
            section_keywords = [k.strip() for k in section_keywords.split(',') if k.strip()]

        # 收集段落的 keywords
        para_keywords_all = []
        for para in sec.get("paragraphs", []):
            para_kw = para.get("keywords", [])
            if isinstance(para_kw, str):
                para_kw = [k.strip() for k in para_kw.split(',') if k.strip()]
            para_keywords_all.extend(para_kw)

        # 组合搜索关键词
        # V32.4: 先加综述主题核心关键词，再加章节关键词，再加段落关键词
        search_keywords = []
        if topic_keywords:
            search_keywords.extend(topic_keywords)
        if section_keywords:
            search_keywords.extend(section_keywords)
        if para_keywords_all:
            search_keywords.extend(para_keywords_all)

        # 如果没有 keywords，就用标题和段落主题
        if not search_keywords:
            search_keywords = [sec_title]
            for para in sec.get("paragraphs", []):
                para_topic = para.get("topic", "").strip()
                if para_topic and para_topic not in search_keywords:
                    search_keywords.append(para_topic)

        # 去重 + 收窄：优先专有名词，限制在 3 个词以内（避免 inflammation 这类泛词稀释）
        search_keywords = list(dict.fromkeys(search_keywords))
        query = build_section_query(search_keywords, title=sec_title)

        print(f"\n  [{sec_idx+1}/{num_sections}] 章节: {sec_title[:40]}")
        print(f"    搜索关键词: {query.split()}")
        print(f"    搜索查询: {query[:60]}...")

        # 按章节关键词搜索
        try:
            result = retriever.retrieve(
                query=query,
                top_paragraphs=papers_per_section * 6,  # 多搜一些，供相关性过滤
                top_figures=0,
            )
            paragraphs = result.get("paragraphs", [])
            bucket = outline.setdefault("timings", {})
            for key, value in (result.get("timings") or {}).items():
                bucket[key] = round(float(bucket.get(key) or 0) + float(value or 0), 1)
            bucket["sections"] = int(bucket.get("sections") or 0) + 1
            query_terms = query.split()
            paper_texts: dict[str, str] = {}

            # V31.83: 收集这个章节的论文和证据卡片（去重，按搜索排名）
            sec_paper_ids = []
            sec_evidence_ids = []
            paper_scores: dict[str, float] = {}
            for p in paragraphs:
                pid = p.get("paper_id", "")
                if not pid:
                    continue
                if pid not in all_papers:
                    all_papers[pid] = {
                        "paper_id": pid,
                        "title": p.get("paper_title", pid),
                        "source": p.get("source", "full_text"),
                    }
                if pid not in sec_paper_ids:
                    sec_paper_ids.append(pid)
                paper_scores[pid] = max(
                    paper_scores.get(pid, 0.0), float(p.get("score") or 0.0)
                )
                paper_texts[pid] = (
                    paper_texts.get(pid, "")
                    + " "
                    + str(p.get("paper_title", ""))
                    + " "
                    + str(p.get("content") or p.get("text") or "")
                )

                # V31.83: 从段落构造证据卡片，直接分配到章节
                para_id = p.get("para_id", f"{pid}_para_{len(sec_evidence_ids)}")
                evidence_id = f"ev_{pid}_{para_id}_{evidence_seq}"
                evidence_seq += 1

                if evidence_id not in all_evidence_cards:
                    content = p.get("content", "") or p.get("text", "") or p.get("paper_title", pid)
                    if len(content) > 1000:
                        content = content[:1000] + "..."
                    all_evidence_cards[evidence_id] = {
                        "evidence_id": evidence_id,
                        "paper_id": pid,
                        "para_id": para_id,
                        "paper_title": p.get("paper_title", pid),
                        "section_l1": p.get("section_l1", ""),
                        "page": p.get("page", 0),
                        "content": content,
                        "original_quote": content[:200],
                        "confidence": 0.8,
                        "verified": False,
                        "source_type": "full_text",  # V33.17: 全文证据
                    }

                if evidence_id not in sec_evidence_ids:
                    sec_evidence_ids.append(evidence_id)

            # V33.17: 摘要回退 —— 无全文段落的论文，把摘要当作一条证据
            # 规则：
            #   1) 摘要命中且全文库无同 DOI 论文 → 摘要当一条证据（paper.source = abstract）
            #   2) 摘要命中且全文库有同 DOI 论文 → 摘要证据合并到全文 paper_id 名下（去重）
            #   3) 纯摘要论文数量上限 papers_per_section，避免章节论文数爆炸
            abstracts = []
            abstract_searcher = getattr(retriever, "abstract_searcher", None)
            if abstract_searcher is not None:
                try:
                    abstracts = abstract_searcher.search(query, top_k=papers_per_section * 3)
                except Exception as e:
                    print(f"    ⚠️  V33.17 摘要库检索失败: {e}")
                    abstracts = []

            if abstracts:
                doi_map = _get_fulltext_doi_map()
                abstract_added = 0
                for a in abstracts:
                    pmid = (a.get("pmid", "") or a.get("paper_id", "") or "").strip()
                    if not pmid:
                        continue
                    abstract_text = (a.get("abstract", "") or "").strip()
                    if len(abstract_text) < 50:
                        continue  # 摘要太短，没有证据价值

                    # DOI 去重：全文库里有同一篇论文 → 归到全文 paper_id 名下
                    doi = (a.get("doi", "") or "").strip().lower()
                    fulltext_pid = doi_map.get(doi, "") if doi else ""
                    if fulltext_pid:
                        target_pid = fulltext_pid
                    else:
                        # 纯摘要论文数量上限控制
                        if len(sec_paper_ids) >= papers_per_section * 2:
                            break
                        target_pid = pmid

                    if target_pid not in all_papers:
                        all_papers[target_pid] = {
                            "paper_id": target_pid,
                            "title": a.get("title", target_pid),
                            "source": "full_text" if fulltext_pid else "abstract",  # V33.17: 标注来源
                        }
                    if target_pid not in sec_paper_ids:
                        sec_paper_ids.append(target_pid)
                    paper_texts[target_pid] = (
                        paper_texts.get(target_pid, "")
                        + " "
                        + str(a.get("title", ""))
                        + " "
                        + abstract_text
                    )

                    para_id = f"abstract_{pmid}"
                    evidence_id = f"ev_{target_pid}_{para_id}_{evidence_seq}"
                    evidence_seq += 1
                    if evidence_id not in all_evidence_cards:
                        content = abstract_text[:1000] + ("..." if len(abstract_text) > 1000 else "")
                        all_evidence_cards[evidence_id] = {
                            "evidence_id": evidence_id,
                            "paper_id": target_pid,
                            "para_id": para_id,
                            "paper_title": a.get("title", target_pid),
                            "section_l1": "Abstract",
                            "page": 0,
                            "content": content,
                            "original_quote": content[:200],
                            "confidence": 0.6,  # V33.17: 摘要证据置信度低于全文段落
                            "verified": False,
                            "source_type": "abstract",  # V33.17: 标注摘要证据
                        }
                    if evidence_id not in sec_evidence_ids:
                        sec_evidence_ids.append(evidence_id)
                    abstract_added += 1
                if abstract_added:
                    print(f"    📄 V33.17 摘要回退：补充 {abstract_added} 条摘要证据")

            # 标题召回通道：把「标题就命中查询词」的论文拉进候选（绕开段落级漂移）
            title_ids: set[str] = set()
            db_path = _research_db_path()
            if db_path is not None:
                recall_limit, recall_max = _title_recall_limits()
                try:
                    extras = title_recall.recall(db_path, query_terms, limit=recall_limit)
                except Exception:
                    extras = []
                added = 0
                for item in extras:
                    pid = item["paper_id"]
                    if pid in sec_paper_ids or added >= recall_max:
                        continue
                    for row in item["paragraphs"]:
                        evidence_id = f"ev_title_{pid}_{row['para_id'][-8:]}_{evidence_seq}"
                        evidence_seq += 1
                        content = row["text"][:1000]
                        all_evidence_cards[evidence_id] = {
                            "evidence_id": evidence_id,
                            "paper_id": pid,
                            "para_id": row["para_id"],
                            "paper_title": row["paper_title"],
                            "section_l1": row["section_l1"],
                            "page": 0,
                            "content": content,
                            "original_quote": content[:200],
                            "confidence": 0.75,
                            "verified": False,
                            "source_type": "title_match",
                        }
                        sec_evidence_ids.append(evidence_id)
                    sec_paper_ids.append(pid)
                    title_ids.add(pid)
                    paper_scores[pid] = max(paper_scores.get(pid, 0.0), 1.0)
                    all_papers[pid] = {
                        "paper_id": pid,
                        "title": item["paragraphs"][0].get("paper_title", pid),
                        "source": "title_match",
                    }
                    added += 1
                if added:
                    print(f"    🔎 标题召回：补充 {added} 篇")

            # 摘要库标题召回：覆盖没有全文、但有摘要的论文
            abstract_db = Path(__file__).resolve().parent.parent.parent / "data" / "abstracts.db"
            if abstract_db.exists():
                try:
                    pmids = title_recall.recall_abstracts_by_title(
                        abstract_db, query_terms, limit=6
                    )
                except Exception:
                    pmids = []
                added_abs = 0
                for pmid in pmids:
                    if pmid in sec_paper_ids or added_abs >= 2:
                        continue
                    record = title_recall.abstract_for(abstract_db, pmid, query_terms)
                    if not record:
                        continue
                    evidence_id = f"ev_abs_title_{pmid}_{evidence_seq}"
                    evidence_seq += 1
                    content = record["abstract"][:1000]
                    all_evidence_cards[evidence_id] = {
                        "evidence_id": evidence_id,
                        "paper_id": pmid,
                        "para_id": f"{pmid}_abstract",
                        "paper_title": record["title"],
                        "section_l1": "Abstract",
                        "page": 0,
                        "content": content,
                        "original_quote": content[:200],
                        "confidence": 0.6,
                        "verified": False,
                        "source_type": "abstract_title_match",
                    }
                    sec_evidence_ids.append(evidence_id)
                    sec_paper_ids.append(pmid)
                    title_ids.add(pmid)
                    paper_scores[pmid] = max(paper_scores.get(pmid, 0.0), 0.5)
                    all_papers[pmid] = {
                        "paper_id": pmid,
                        "title": record["title"],
                        "source": "abstract_title_match",
                    }
                    added_abs += 1
                if added_abs:
                    print(f"    🔎 摘要标题召回：补充 {added_abs} 篇")

            # 相关性过滤：多词查询至少命中 2 个词；单词查询命中 1 个即可
            relevant = [
                pid
                for pid in sec_paper_ids
                if pid in title_ids
                or is_paper_relevant(paper_texts.get(pid, ""), query_terms)
            ]
            if relevant and len(relevant) < len(sec_paper_ids):
                dropped = len(sec_paper_ids) - len(relevant)
                sec_paper_ids = relevant
                sec_evidence_ids = [
                    eid
                    for eid in sec_evidence_ids
                    if all_evidence_cards.get(eid, {}).get("paper_id") in relevant
                ]
                print(f"    🎯 相关性过滤：保留 {len(relevant)} 篇，剔除 {dropped} 篇")

            # 标题命中优先排序（保留全部候选，只影响上限截断时谁留下）
            titles = _paper_titles(sec_paper_ids)
            for pid, title in titles.items():
                if title and pid in all_papers and all_papers[pid].get("title") in (pid, "", None):
                    all_papers[pid]["title"] = title
            sec_paper_ids = rank_papers(sec_paper_ids, titles, query_terms, paper_scores)

            # 每章论文上限
            if len(sec_paper_ids) > papers_per_section:
                sec_paper_ids = sec_paper_ids[:papers_per_section]
                sec_evidence_ids = [
                    eid
                    for eid in sec_evidence_ids
                    if all_evidence_cards.get(eid, {}).get("paper_id") in sec_paper_ids
                ]

            # V31.83: 直接分配论文ID和证据ID到这个章节
            sec["assigned_paper_ids"] = sec_paper_ids
            sec["assigned_evidence_ids"] = sec_evidence_ids
            total_assigned += len(sec_paper_ids)
            print(f"    ✅ 分配 {len(sec_paper_ids)} 篇论文，{len(sec_evidence_ids)} 条证据卡片到这个章节")

            # 段落级分配：按段落主题匹配
            for para in sec.get("paragraphs", []):
                para_topic = para.get("topic", "").strip()
                para_keywords = set(para_topic.lower().split())

                para_papers = []
                para_evidences = []
                for pid in sec_paper_ids:
                    paper = all_papers.get(pid, {})
                    title = paper.get("title", "")
                    paper_keywords = set(title.lower().split())
                    overlap = len(paper_keywords & para_keywords)
                    if overlap > 0:
                        para_papers.append(pid)

                # 如果段落没有匹配到论文，就分配这个章节的前2篇
                if not para_papers and sec_paper_ids:
                    para_papers = sec_paper_ids[:2]

                # V31.83: 分配证据卡片：匹配论文ID的证据卡片
                for eid in sec_evidence_ids:
                    ev = all_evidence_cards.get(eid, {})
                    if ev.get("paper_id") in para_papers:
                        para_evidences.append(eid)

                # 如果段落没有匹配到证据卡片，就分配这个章节的前4条
                if not para_evidences and sec_evidence_ids:
                    para_evidences = sec_evidence_ids[:4]

                para["assigned_paper_ids"] = para_papers
                para["assigned_evidence_ids"] = para_evidences

        except Exception as e:
            print(f"    ⚠️  搜索失败: {e}")
            import traceback
            traceback.print_exc()
            sec["assigned_paper_ids"] = []
            sec["assigned_evidence_ids"] = []
            continue

        # 总数控制：如果已经达到 max_papers，就停止
        if total_assigned >= max_papers:
            print(f"\n⚠️  已达到最大论文数 {max_papers}，停止搜索")
            break

    # V33.17: 统计每篇论文的证据数（区分全文/摘要，供前端显示）
    evidence_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"fulltext": 0, "abstract": 0})
    for ev in all_evidence_cards.values():
        if ev.get("source_type") == "abstract":
            evidence_counts[ev["paper_id"]]["abstract"] += 1
        else:
            evidence_counts[ev["paper_id"]]["fulltext"] += 1
    for pid, paper in all_papers.items():
        c = evidence_counts.get(pid)
        paper["evidence_count"] = (c["fulltext"] + c["abstract"]) if c else 0
        paper["fulltext_evidence_count"] = c["fulltext"] if c else 0
        paper["abstract_evidence_count"] = c["abstract"] if c else 0

    papers = list(all_papers.values())
    evidence_cards = list(all_evidence_cards.values())

    # V31.83: 把证据卡片保存到 outline 里，generate 函数可以直接用
    outline["evidence_cards"] = evidence_cards

    abstract_paper_count = sum(1 for p in papers if p.get("source") == "abstract")
    abstract_evidence_count = sum(c["abstract"] for c in evidence_counts.values())
    print(f"\n✅ 搜索完成：共 {len(papers)} 篇论文（其中摘要库论文 {abstract_paper_count} 篇），"
          f"{len(evidence_cards)} 条证据卡片（其中摘要证据 {abstract_evidence_count} 条），分配 {total_assigned} 篇次")

    return outline, papers
