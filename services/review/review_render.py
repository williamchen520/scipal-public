"""Markdown/reference rendering mixin for ReviewGenerator."""

from __future__ import annotations

from .citation_formatter import (
    PaperMetadata,
    build_metadata_from_db_row,
    format_citation,
    format_citation_list,
    get_missing_fields_report,
)
from .models import EvidenceCard, ReviewDraft


class ReviewRenderMixin:
    @staticmethod
    def _format_ref_numbers(numbers: list[int]) -> str:
        """
        V25.18: 格式化参考文献编号，支持连续编号合并。

        例如：
        - [1, 2, 3] → "[1-3]"
        - [1, 3, 5] → "[1,3,5]"
        - [1, 2, 4, 5, 6] → "[1-2,4-6]"
        - [1] → "[1]"
        """
        if not numbers:
            return ""

        sorted_nums = sorted(set(numbers))
        if len(sorted_nums) == 1:
            return f"[{sorted_nums[0]}]"

        # 合并连续编号
        ranges = []
        start = sorted_nums[0]
        end = sorted_nums[0]

        for n in sorted_nums[1:]:
            if n == end + 1:
                end = n
            else:
                ranges.append((start, end))
                start = n
                end = n
        ranges.append((start, end))

        # 格式化每个区间
        parts = []
        for s, e in ranges:
            if s == e:
                parts.append(str(s))
            else:
                parts.append(f"{s}-{e}")

        return "[" + ",".join(parts) + "]"

    def _render_markdown(
        self,
        topic: str,
        draft: ReviewDraft,
        evidence_dict: dict[str, EvidenceCard],
        conflicts: Optional[list] = None,
        paper_metadata_map: Optional[dict[str, PaperMetadata]] = None,
        citation_style: str = "apa",
        language: str = "en",
    ) -> str:
        """将校验后的 draft 渲染为 Markdown。V25.3: 含研究争议章节。V25.7: 多格式参考文献格式化。V25.9: 支持英文/中文标题。V25.18: 正文引用从证据ID改为参考文献编号，按出现顺序编号。"""
        lines = [f"# {topic}", ""]

        # V25.18: 建立 evidence_id → 参考文献编号映射（按正文首次出现顺序）
        evidence_to_ref = {}  # evidence_id -> ref_number
        paper_to_ref = {}     # paper_id -> ref_number
        ref_paper_ids_ordered = []  # 按出现顺序排列的 paper_id
        ref_counter = 0

        for section in draft.outline.sections:
            section_sents = draft.sentences_by_section(section.section_id)
            valid_sents = [
                s for s in section_sents
                if s.status in (SentenceStatus.VERIFIED, SentenceStatus.CONTROVERSIAL)
            ]
            for sent in valid_sents:
                for eid in sent.evidence_ids:
                    if eid in evidence_dict and eid not in evidence_to_ref:
                        pid = (evidence_dict[eid].paper_id or "").strip()
                        if pid:
                            if pid not in paper_to_ref:
                                ref_counter += 1
                                paper_to_ref[pid] = ref_counter
                                ref_paper_ids_ordered.append(pid)
                            evidence_to_ref[eid] = paper_to_ref[pid]

        # V25.18: 把研究争议中引用的 evidence_id 也加入映射
        if conflicts:
            for conflict in conflicts:
                for side in getattr(conflict, 'sides', []) or []:
                    for eid in side.get('evidence_ids', []) or []:
                        if eid in evidence_dict and eid not in evidence_to_ref:
                            pid = (evidence_dict[eid].paper_id or "").strip()
                            if pid:
                                if pid not in paper_to_ref:
                                    ref_counter += 1
                                    paper_to_ref[pid] = ref_counter
                                    ref_paper_ids_ordered.append(pid)
                                evidence_to_ref[eid] = paper_to_ref[pid]

        for section in draft.outline.sections:
            section_sents = draft.sentences_by_section(section.section_id)
            # 只保留已验证和有争议的句子，剔除被拒绝的
            valid_sents = [
                s for s in section_sents
                if s.status in (SentenceStatus.VERIFIED, SentenceStatus.CONTROVERSIAL)
            ]
            if not valid_sents:
                continue

            lines.append(f"## {section.title}")
            lines.append("")

            for sent in valid_sents:
                line = sent.text
                # V25.18: 把证据 ID 引用转换成参考文献编号
                if sent.evidence_ids:
                    ref_numbers = sorted(set(
                        evidence_to_ref[eid] for eid in sent.evidence_ids
                        if eid in evidence_to_ref
                    ))
                    if ref_numbers:
                        citation_str = self._format_ref_numbers(ref_numbers)
                        line = f"{line} {citation_str}"
                if sent.status == SentenceStatus.CONTROVERSIAL:
                    controversial_label = "⚠️ (controversial)" if language.lower() == "en" else "⚠️（存在争议）"
                    line = f"{line} {controversial_label}"
                lines.append(line)
                lines.append("")

        # V25.5: 研究争议章节（区分真正矛盾和条件差异型，生成两个章节）
        if conflicts:
            # 分组
            true_controversies = [c for c in conflicts if getattr(c, 'conflict_type', 'true_controversy') == 'true_controversy']
            condition_differences = [c for c in conflicts if getattr(c, 'conflict_type', 'true_controversy') == 'condition_difference']

            if language.lower() == "en":
                # 章节1：真正矛盾
                if true_controversies:
                    lines.append("## Research Controversies and Inconsistencies")
                    lines.append("")
                    for i, conflict in enumerate(true_controversies, 1):
                        lines.append(f"### {i}. {conflict.topic}")
                        lines.append("")
                        if conflict.summary:
                            lines.append(conflict.summary)
                            lines.append("")
                        if conflict.condition_analysis:
                            lines.append(f"**Experimental condition difference analysis**: {conflict.condition_analysis}")
                            lines.append("")
                        if conflict.sides:
                            lines.append("**Viewpoints from all sides**:")
                            lines.append("")
                            for side in conflict.sides:
                                ref_nums = sorted(set(evidence_to_ref[eid] for eid in side.get('evidence_ids', []) if eid in evidence_to_ref))
                                eids = self._format_ref_numbers(ref_nums) if ref_nums else ""
                                lines.append(f"- {side.get('side', 'Viewpoint')}: {side.get('claim', '')} {eids}")
                            lines.append("")

                # 章节2：条件差异型
                if condition_differences:
                    lines.append("## Result Differences Under Different Experimental Conditions")
                    lines.append("")
                    lines.append("The following result differences primarily arise from variations in experimental conditions (e.g., mutation type, cell type, measurement endpoint, stimulus conditions), rather than genuine academic controversy.")
                    lines.append("")
                    for i, conflict in enumerate(condition_differences, 1):
                        lines.append(f"### {i}. {conflict.topic}")
                        lines.append("")
                        if conflict.summary:
                            lines.append(conflict.summary)
                            lines.append("")
                        if conflict.condition_analysis:
                            lines.append(f"**Condition difference analysis**: {conflict.condition_analysis}")
                            lines.append("")
                        if conflict.sides:
                            lines.append("**Results under each condition**:")
                            lines.append("")
                            for side in conflict.sides:
                                ref_nums = sorted(set(evidence_to_ref[eid] for eid in side.get('evidence_ids', []) if eid in evidence_to_ref))
                                eids = self._format_ref_numbers(ref_nums) if ref_nums else ""
                                lines.append(f"- {side.get('side', 'Condition')}: {side.get('claim', '')} {eids}")
                            lines.append("")
            else:
                # 中文标题（向后兼容）
                if true_controversies:
                    lines.append("## 研究争议与不一致")
                    lines.append("")
                    for i, conflict in enumerate(true_controversies, 1):
                        lines.append(f"### {i}. {conflict.topic}")
                        lines.append("")
                        if conflict.summary:
                            lines.append(conflict.summary)
                            lines.append("")
                        if conflict.condition_analysis:
                            lines.append(f"**实验条件差异分析**：{conflict.condition_analysis}")
                            lines.append("")
                        if conflict.sides:
                            lines.append("**各方观点**：")
                            lines.append("")
                            for side in conflict.sides:
                                ref_nums = sorted(set(evidence_to_ref[eid] for eid in side.get('evidence_ids', []) if eid in evidence_to_ref))
                                eids = self._format_ref_numbers(ref_nums) if ref_nums else ""
                                lines.append(f"- {side.get('side', '观点')}：{side.get('claim', '')} {eids}")
                            lines.append("")

                if condition_differences:
                    lines.append("## 不同实验条件下的结果差异")
                    lines.append("")
                    lines.append("以下结果差异主要源于实验条件的不同（如突变类型、细胞类型、测量指标、刺激条件等），并非真正的学术争议。")
                    lines.append("")
                    for i, conflict in enumerate(condition_differences, 1):
                        lines.append(f"### {i}. {conflict.topic}")
                        lines.append("")
                        if conflict.summary:
                            lines.append(conflict.summary)
                            lines.append("")
                        if conflict.condition_analysis:
                            lines.append(f"**条件差异分析**：{conflict.condition_analysis}")
                            lines.append("")
                        if conflict.sides:
                            lines.append("**各条件下的结果**：")
                            lines.append("")
                            for side in conflict.sides:
                                ref_nums = sorted(set(evidence_to_ref[eid] for eid in side.get('evidence_ids', []) if eid in evidence_to_ref))
                                eids = self._format_ref_numbers(ref_nums) if ref_nums else ""
                                lines.append(f"- {side.get('side', '条件')}：{side.get('claim', '')} {eids}")
                            lines.append("")

        # 参考文献（V25.7: CSL 引擎渲染，专业样式，零幻觉。V25.18: 按正文出现顺序编号）
        refs_title = "## References" if language.lower() == "en" else "## 参考文献"
        lines.append(refs_title)
        lines.append("")

        # V25.18: 使用按正文出现顺序排列的 paper_id（前面已建立 ref_paper_ids_ordered）
        # 如果没有（极端情况），回退到从 evidence_dict 收集
        if not ref_paper_ids_ordered:
            seen_pids = set()
            for card in evidence_dict.values():
                pid = (card.paper_id or "").strip()
                if pid and pid not in seen_pids:
                    seen_pids.add(pid)
                    ref_paper_ids_ordered.append(pid)

        # 按出现顺序收集元数据
        ref_metadata_list = []
        if paper_metadata_map:
            for pid in ref_paper_ids_ordered:
                if pid in paper_metadata_map:
                    ref_metadata_list.append(paper_metadata_map[pid])

        # 用 CSL 引擎批量渲染
        if ref_metadata_list:
            try:
                formatted_refs = format_citation_list(ref_metadata_list, style=citation_style)
                for i, ref_str in enumerate(formatted_refs, 1):
                    # V25.18: 加编号前缀，和正文引用对应
                    lines.append(f"{i}. {ref_str}")
            except Exception as e:
                # CSL 引擎渲染失败，降级为简单格式
                print(f"⚠️  CSL 引擎渲染失败，降级为简单格式: {e}")
                for i, pid in enumerate(ref_paper_ids_ordered, 1):
                    card = next((c for c in evidence_dict.values() if c.paper_id == pid), None)
                    title = card.paper_title if card else pid
                    lines.append(f"{i}. [{pid}] {title}")
        else:
            # 没有元数据，用简单格式
            for i, pid in enumerate(ref_paper_ids_ordered, 1):
                card = next((c for c in evidence_dict.values() if c.paper_id == pid), None)
                title = card.paper_title if card else pid
                lines.append(f"{i}. [{pid}] {title}")

        lines.append("")

        return "\n".join(lines)

    def _fetch_paper_metadata(self, evidence_cards: list[EvidenceCard]) -> dict[str, PaperMetadata]:
        """从 PostgreSQL 查询论文元数据，用于 GB/T 7714 参考文献格式化。"""
        metadata_map = {}
        paper_ids = set()
        for card in evidence_cards:
            pid = (card.paper_id or "").strip()
            if pid:
                paper_ids.add(pid)
        if not paper_ids:
            return metadata_map
        from services.db.pg_pool import main_read_connection

        pg = main_read_connection()
        try:
            rows = pg.execute(
                "SELECT paper_id, title, authors, journal, year, doi "
                "FROM papers WHERE paper_id = ANY(%s)",
                (list(paper_ids),),
            ).fetchall()
        finally:
            pg.close()
        for row in rows:
            metadata = build_metadata_from_db_row(dict(row))
            metadata_map[metadata.paper_id] = metadata
        return metadata_map

    def _build_references(self, evidence_cards: list[EvidenceCard], paper_metadata_map: Optional[dict[str, PaperMetadata]] = None, citation_style: str = "apa") -> list[dict]:
        """构建参考文献列表（V25.1: 过滤空 paper_id；V25.7: CSL引擎格式化字符串）。"""
        seen = set()
        refs = []
        metadata_list = []

        for card in evidence_cards:
            pid = (card.paper_id or "").strip()
            if not pid or pid in seen:
                continue
            seen.add(pid)
            ref_entry = {
                "paper_id": pid,
                "title": card.paper_title or pid,
                "section": card.section_l1,
            }
            refs.append(ref_entry)
            if paper_metadata_map and pid in paper_metadata_map:
                metadata_list.append(paper_metadata_map[pid])
                # 检查缺失字段
                missing = get_missing_fields_report(paper_metadata_map[pid])
                if missing:
                    ref_entry["missing_fields"] = missing

        # 用 CSL 引擎批量渲染格式化字符串
        if metadata_list:
            try:
                formatted_refs = format_citation_list(metadata_list, style=citation_style)
                for i, ref_entry in enumerate(refs):
                    if i < len(formatted_refs):
                        ref_entry["formatted"] = formatted_refs[i]
            except Exception as e:
                print(f"⚠️  CSL 引擎渲染参考文献失败: {e}")

        return refs


# ──────────────────────────────────────────────
# 自测（不依赖 LLM 和检索，测试数据结构和渲染）
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("📝 Review Generator Test (V25.0)")
    print("=" * 60)

    # 构造测试证据
    cards = [
        EvidenceCard(
            evidence_id="ev_p1_para1_0",
            paper_id="paper1",
            para_id="para1",
            paper_title="STAT1 and interferon immunity",
            content="STAT1 is phosphorylated at Y701 by JAK kinases in response to IFN-gamma.",
            evidence_type=EvidenceType.MECHANISM,
        ),
        EvidenceCard(
            evidence_id="ev_p1_para2_0",
            paper_id="paper1",
            para_id="para2",
            paper_title="STAT1 and interferon immunity",
            content="STAT1 forms homodimers (GAF) that bind GAS elements to induce target gene transcription.",
            evidence_type=EvidenceType.MECHANISM,
        ),
        EvidenceCard(
            evidence_id="ev_p2_para1_0",
            paper_id="paper2",
            para_id="para1",
            paper_title="JAK-STAT pathway in disease",
            content="STAT1 knockout mice are highly susceptible to viral and mycobacterial infections.",
            evidence_type=EvidenceType.FACT,
        ),
    ]

    # 测试简单大纲生成
    print("\n--- 简单大纲生成测试 ---")
    # 创建一个无 LLM、无检索的 generator（只测试大纲和渲染）
    generator = ReviewGenerator.__new__(ReviewGenerator)
    generator.max_evidence_per_paper = 5
    generator.use_llm_verification = False

    outline = generator._generate_simple_outline("STAT1 干扰素调控", cards)
    print(f"  主题: {outline.topic}")
    print(f"  章节数: {len(outline.sections)}")
    for sec in outline.sections:
        print(f"    [{sec.section_id}] {sec.title} ({len(sec.assigned_evidence_ids)} 条证据)")

    # 测试 Markdown 渲染
    print("\n--- Markdown 渲染测试 ---")
    evidence_dict = {c.evidence_id: c for c in cards}

    # 构造一个模拟 draft
    from .models import ReviewSentence, SentenceStatus
    test_draft = ReviewDraft(
        topic="STAT1 干扰素调控",
        outline=outline,
        sentences=[
            ReviewSentence(
                sentence_id="sent_sec_00_0",
                section_id="sec_00",
                text="STAT1 在 IFN-gamma 刺激下被 JAK 激酶磷酸化于 Y701 位点。",
                evidence_ids=["ev_p1_para1_0"],
                status=SentenceStatus.VERIFIED,
            ),
            ReviewSentence(
                sentence_id="sent_sec_00_1",
                section_id="sec_00",
                text="磷酸化的 STAT1 形成同源二聚体 GAF，结合 GAS 元件诱导靶基因转录。",
                evidence_ids=["ev_p1_para2_0"],
                status=SentenceStatus.VERIFIED,
            ),
            ReviewSentence(
                sentence_id="sent_sec_01_0",
                section_id="sec_01",
                text="STAT1 敲除小鼠对病毒和分枝杆菌感染高度易感。",
                evidence_ids=["ev_p2_para1_0"],
                status=SentenceStatus.VERIFIED,
            ),
            ReviewSentence(
                sentence_id="sent_sec_01_1",
                section_id="sec_01",
                text="这是一句编造的无证据结论。",
                evidence_ids=[],
                status=SentenceStatus.REJECTED,
                verification_note="无证据ID",
            ),
        ],
        evidence_cards=evidence_dict,
    )

    markdown = generator._render_markdown("STAT1 干扰素调控", test_draft, evidence_dict)
    print(markdown[:800])
    print("...")

    # 测试句子拆分和证据关联
    print("\n--- 句子拆分与证据关联测试 ---")
    test_text = "STAT1 is phosphorylated at Y701 [ev_p1_para1_0]. It forms GAF dimers [ev_p1_para2_0]. Knockout mice are susceptible [ev_p2_para1_0]."
    split_sents = generator._split_and_link(test_text, "sec_00", cards, 0)
    for s in split_sents:
        print(f"  [{s.sentence_id}] evidence={s.evidence_ids} — {s.text[:50]}")

    print("\n✅ 数据结构和渲染测试通过。")
    print("   完整生成流程需要 Ollama 服务 + 检索层运行。")
    print("   启动后可通过 API: POST /api/review/generate")


# ──────────────────────────────────────────────
# V26.1: 自动发配论文到章节
# ──────────────────────────────────────────────
