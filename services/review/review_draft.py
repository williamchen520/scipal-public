"""Draft writing/section review mixin for ReviewGenerator."""

from __future__ import annotations

from .llm_client import LLMError
from .models import (
    EvidenceCard,
    ReviewDraft,
    ReviewOutline,
    ReviewParagraph,
    ReviewSection,
    ReviewSentence,
    SentenceStatus,
)
from .review_prompts import WRITE_SYSTEM_PROMPT_EN, WRITE_SYSTEM_PROMPT_ZH
from .section_loop import write_section_loop
from .section_prompts import build_write_prompt


class ReviewDraftMixin:
    def _write_draft(
        self,
        topic: str,
        outline: ReviewOutline,
        evidence_dict: dict[str, EvidenceCard],
        review_type: str = "narrative",
        language: str = "en",
    ) -> ReviewDraft:
        """
        撰写综述初稿。V25.0 用 LLM 基于证据卡片写每个章节。
        V25.7: 支持三种综述模板（narrative/comparative/systematic）。
        V25.8: 支持段落级大纲——如果章节有 paragraphs，按段落撰写；否则按章节撰写。
        V25.9: 支持 language 参数（默认英文）。
        """
        all_sentences: list[ReviewSentence] = []
        sent_seq = 0
        # V32.5: 渐进式上下文注入——维护前文摘要，避免章节间重复、保持连贯
        previous_sections_summary = ""

        print(f"✍️  开始撰写正文，共 {len(outline.sections)} 个章节...")
        # V33.4: 证据不足 fallback —— 记录证据不足的章节，用于最终警告
        insufficient_evidence_sections: list[str] = []
        MIN_EVIDENCE_PER_SECTION = 2  # 每章最少证据数，低于此值触发 fallback

        for sec_idx, section in enumerate(outline.sections):
            # V31.8: 不管有没有段落级大纲，都按章节写（减少调用次数）
            section_evidence = [
                evidence_dict[eid] for eid in section.assigned_evidence_ids
                if eid in evidence_dict
            ]
            print(f"  [{sec_idx+1}/{len(outline.sections)}] {section.title[:40]}: {len(section_evidence)} 条证据")

            # V33.4: 证据不足 fallback 机制
            if not section_evidence or len(section_evidence) < MIN_EVIDENCE_PER_SECTION:
                if not section_evidence:
                    print(f"    ⚠️  没有证据，触发 fallback（生成综述性描述）")
                else:
                    print(f"    ⚠️  证据不足（{len(section_evidence)} < {MIN_EVIDENCE_PER_SECTION}），触发 fallback")
                insufficient_evidence_sections.append(section.title)

                # V33.4: 降级生成——基于章节标题和描述生成综述性概述
                # 明确标注"本章直接证据有限"，避免幻觉
                fallback_text = self._generate_fallback_section(
                    section, review_type=review_type, language=language,
                    previous_summary=previous_sections_summary,
                    section_index=sec_idx, total_sections=len(outline.sections),
                )
                if fallback_text and len(fallback_text) > 50:
                    print(f"    ✅ Fallback 生成完成，{len(fallback_text)} 字符")
                    # V33.4: 更新前文摘要
                    section_summary = fallback_text[:200].replace("\n", " ")
                    if previous_sections_summary:
                        previous_sections_summary = (previous_sections_summary + " | " + section_summary)[-800:]
                    else:
                        previous_sections_summary = section_summary

                    # V33.4: fallback 章节不做证据引用关联（因为没有证据）
                    # 直接把整段作为一个句子，标记为"无直接证据"
                    fallback_sentence = ReviewSentence(
                        sentence_id=f"sent_{section.section_id}_0",
                        section_id=section.section_id,
                        text=fallback_text,
                        evidence_ids=[],
                        status=SentenceStatus.UNVERIFIED,
                        verification_note="证据不足 fallback 章节：无直接证据支撑，为综述性概述",
                    )
                    all_sentences.append(fallback_sentence)
                    sent_seq += 1
                continue

            print(f"    正在调用 LLM 撰写此章节...")

            # B5c: 写作-评审-重试的循环已抽到 section_loop（返回最佳尝试）
            def _generate(feedback: str) -> str:
                return self._write_section(
                    section, section_evidence,
                    review_type=review_type, language=language,
                    previous_summary=previous_sections_summary,
                    section_index=sec_idx,
                    total_sections=len(outline.sections),
                    feedback=feedback,
                )

            def _review(text: str):
                return self._review_section(section, text, section_evidence, language=language)

            attempt = write_section_loop(_generate, _review, max_attempts=2)
            section_text = attempt.text
            print(
                f"    ✅ 撰写完成，{len(section_text)} 字符；"
                f"评审 {attempt.score:.0f}/100，尝试 {attempt.attempts} 次"
            )

            # V32.5: 更新前文摘要——截取当前章节前 200 字作为摘要，追加到前文摘要里
            # 为了控制上下文长度，前文摘要最多保留 800 字
            section_summary = section_text[:200].replace("\n", " ")
            if previous_sections_summary:
                previous_sections_summary = (previous_sections_summary + " | " + section_summary)[-800:]
            else:
                previous_sections_summary = section_summary

            sentences = self._split_and_link(
                section_text, section.section_id, section_evidence, sent_seq
            )
            auto_cited = self._auto_cite_sentences(sentences, section_evidence)
            if auto_cited > 0:
                self._auto_cite_count += auto_cited
            all_sentences.extend(sentences)
            sent_seq += len(sentences)

        # V33.4: 保存证据不足的章节列表，供上层调用者获取警告信息
        self._insufficient_evidence_sections = insufficient_evidence_sections
        if insufficient_evidence_sections:
            print(f"\n⚠️  证据不足警告：以下 {len(insufficient_evidence_sections)} 个章节证据不足，已生成综述性概述：")
            for title in insufficient_evidence_sections:
                print(f"    - {title}")
            print("💡  建议：手动为这些章节补充相关文献后重新生成\n")

        return ReviewDraft(
            topic=topic,
            outline=outline,
            sentences=all_sentences,
            evidence_cards=evidence_dict,
        )

    def _generate_fallback_section(
        self,
        section: ReviewSection,
        review_type: str = "narrative",
        language: str = "en",
        previous_summary: str = "",
        section_index: int = 0,
        total_sections: int = 1,
    ) -> str:
        """V33.4: 证据不足时的 fallback 章节生成。

        当章节没有直接证据或证据不足时，不跳过，而是基于章节标题和描述
        生成一段综述性概述，并明确标注"本章直接证据有限"，避免幻觉。

        写作策略：
        1. 明确说明本章直接证据有限，以下为基于相关领域的概述性内容
        2. 基于章节标题和描述，生成该领域的一般性背景知识
        3. 不做具体的实验数据引用（因为没有证据）
        4. 引导读者参考其他章节或进一步查阅文献
        """
        if language.lower() == "en":
            system_prompt = (
                "You are a scientific review writer. When a section has insufficient direct evidence, "
                "write a cautious, general overview based ONLY on the section title and description. "
                "Strict rules:\n"
                "1. Explicitly state that direct evidence for this specific topic is limited\n"
                "2. Write only general background knowledge, no specific experimental data or numbers\n"
                "3. Do NOT cite specific papers or make specific claims that would require evidence\n"
                "4. Suggest that readers consult other sections or further literature for details\n"
                "5. Maintain an academic, cautious tone — avoid overstatement\n"
                "6. Write 150-250 words"
            )

            context_block = ""
            if previous_summary:
                context_block = (
                    f"Previous sections summary (for coherence):\n{previous_summary}\n\n"
                )

            user_prompt = (
                f"## Section with Insufficient Evidence\n\n"
                f"Section title: {section.title}\n"
                f"Section description: {section.description}\n"
                f"Section position: Section {section_index + 1} of {total_sections}\n\n"
                f"{context_block}"
                f"## Important Notice\n"
                f"This section has insufficient direct evidence cards. Write a cautious overview that:\n"
                f"1. Begins by acknowledging the limited direct evidence for this specific topic\n"
                f"2. Provides general background context based on the section title and description\n"
                f"3. Does NOT include specific experimental data, numbers, or paper citations\n"
                f"4. Suggests directions for further reading or references to other sections\n"
                f"5. Maintains academic rigor and avoids unsupported claims\n\n"
                f"Write the section text now (150-250 words)."
            )
        else:
            system_prompt = (
                "你是一个科研综述写作者。当某个章节直接证据不足时，"
                "仅基于章节标题和描述，写一段谨慎的一般性概述。\n"
                "严格规则：\n"
                "1. 明确说明本章针对该具体主题的直接证据有限\n"
                "2. 只写一般性背景知识，不写具体实验数据或数字\n"
                "3. 不引用具体论文，不做出需要证据支撑的具体声明\n"
                "4. 建议读者参考其他章节或进一步查阅文献\n"
                "5. 保持学术、谨慎的语气，避免夸大\n"
                "6. 写 150-250 字"
            )

            context_block = ""
            if previous_summary:
                context_block = f"前文摘要（用于保持连贯）：\n{previous_summary}\n\n"

            user_prompt = (
                f"## 证据不足章节\n\n"
                f"章节标题：{section.title}\n"
                f"章节描述：{section.description}\n"
                f"章节位置：第 {section_index + 1} / {total_sections} 章\n\n"
                f"{context_block}"
                f"## 重要提示\n"
                f"本章直接证据卡片不足。请写一段谨慎的概述：\n"
                f"1. 开头先说明本章针对该具体主题的直接证据有限\n"
                f"2. 基于章节标题和描述，提供一般性背景介绍\n"
                f"3. 不包含具体实验数据、数字或论文引用\n"
                f"4. 建议进一步阅读方向或参考其他章节\n"
                f"5. 保持学术严谨性，避免无依据声明\n\n"
                f"现在开始撰写章节正文（150-250字）。"
            )

        try:
            return self.llm.chat(system_prompt, user_prompt)
        except LLMError as e:
            print(f"⚠️  Fallback 章节 {section.title} 生成失败: {e}")
            # 最终降级：返回一个简单的提示文本
            if language.lower() == "en":
                return (
                    f"### {section.title}\n\n"
                    f"*Note: Direct evidence for this specific topic is currently limited. "
                    f"This section provides general background context only. "
                    f"Readers are encouraged to consult other sections or further literature for detailed information.*\n\n"
                    f"{section.description}\n"
                )
            else:
                return (
                    f"### {section.title}\n\n"
                    f"*注：目前针对该具体主题的直接证据有限。本章仅提供一般性背景介绍。"
                    f"建议读者参考其他章节或进一步查阅文献以获取详细信息。*\n\n"
                    f"{section.description}\n"
                )

    def _collect_paragraph_evidence(
        self,
        paragraph: ReviewParagraph,
        section: ReviewSection,
        evidence_dict: dict[str, EvidenceCard],
    ) -> list[EvidenceCard]:
        """
        V25.8: 收集段落的证据。
        V25.9: 增加第四级回退——无明确分配时使用全部证据（确保综述不为空）。
        优先级：段落分配的证据ID > 段落分配论文的证据 > 章节分配的证据 > 全部证据（兜底）
        """
        # 1. 优先用段落直接分配的证据ID
        if paragraph.assigned_evidence_ids:
            evidence = [
                evidence_dict[eid] for eid in paragraph.assigned_evidence_ids
                if eid in evidence_dict
            ]
            if evidence:
                return evidence

        # 2. 其次用段落分配论文的证据
        if paragraph.assigned_paper_ids:
            evidence = [
                card for card in evidence_dict.values()
                if card.paper_id in paragraph.assigned_paper_ids
            ]
            if evidence:
                return evidence

        # 3. 再次用章节分配的证据
        if section.assigned_evidence_ids:
            evidence = [
                evidence_dict[eid] for eid in section.assigned_evidence_ids
                if eid in evidence_dict
            ]
            if evidence:
                return evidence

        # 4. V25.9 兜底：无任何明确分配时，使用全部证据卡片（每段最多 15 条，避免上下文过长）
        # 这确保即使用户没有手动分配论文，综述也能正常生成
        all_evidence = list(evidence_dict.values())
        if len(all_evidence) > 15:
            # 简单策略：均匀采样，避免每段都用完全相同的前15条
            step = max(1, len(all_evidence) // 15)
            return all_evidence[::step][:15]
        return all_evidence

    def _write_paragraph(
        self,
        paragraph: ReviewParagraph,
        section: ReviewSection,
        evidence: list[EvidenceCard],
        review_type: str = "narrative",
        language: str = "en",
    ) -> str:
        """V25.8: 用 LLM 撰写单个段落（基于段落主题和分配的证据）。V25.9: 支持英文/中文。"""
        # 构建证据上下文
        evidence_text = ""
        for card in evidence:
            evidence_text += f"[{card.evidence_id}] ({card.evidence_type.value}) {card.content}\n"
            if card.original_quote:
                evidence_text += f"  Quote: {card.original_quote[:200]}\n"

        # V25.9: 按语言选择 system prompt 和提示文案
        system_prompt = WRITE_SYSTEM_PROMPT_EN if language.lower() == "en" else WRITE_SYSTEM_PROMPT_ZH

        if language.lower() == "en":
            type_hint = {
                "narrative": "Organize by logical threads, progressing layer by layer, telling the research story clearly.",
                "comparative": "Focus on comparing differences between experimental methods, model systems, and conditions; explicitly state which studies used what methods and reached what different conclusions.",
                "systematic": "Maintain methodological rigor, explicitly describe evidence sources and quality, distinguish facts from inferences, emphasize consistency and differences in evidence.",
            }.get(review_type.lower(), "Organize by logical threads, progressing layer by layer.")

            type_label = {
                "narrative": "Narrative Review",
                "comparative": "Comparative Review",
                "systematic": "Systematic Review",
            }.get(review_type.lower(), "Narrative Review")

            user_prompt = (
                f"Review type: {type_label}\n"
                f"Writing style: {type_hint}\n\n"
                f"Section: {section.title}\n"
                f"Paragraph topic: {paragraph.topic}\n"
                f"Paragraph description: {paragraph.description or '(none)'}\n\n"
                f"Available evidence cards:\n{evidence_text}\n\n"
                f"Based on the above evidence cards, write one paragraph of review text (100-200 words) on the topic \"{paragraph.topic}\". "
                f"Every declarative sentence must end with a [evidence_id] citation marker. "
                f"Write only this paragraph's content, no paragraph title, no other paragraphs."
            )
        else:
            type_hint = {
                "narrative": "按逻辑线索组织，层层递进，像讲故事一样把研究脉络讲清楚。",
                "comparative": "重点对比不同实验方法、模型系统和实验条件之间的差异，明确指出哪些研究用了什么方法、得出了什么不同结论。",
                "systematic": "保持方法学严谨性，明确描述证据来源和质量，区分事实和推断，强调证据的一致性和差异性。",
            }.get(review_type.lower(), "按逻辑线索组织，层层递进。")

            type_label = {
                "narrative": "叙事型综述",
                "comparative": "实验对比型综述",
                "systematic": "系统综述型",
            }.get(review_type.lower(), "叙事型综述")

            user_prompt = (
                f"综述模板类型：{type_label}\n"
                f"写作风格要求：{type_hint}\n\n"
                f"所属章节：{section.title}\n"
                f"段落主题：{paragraph.topic}\n"
                f"段落描述：{paragraph.description or '（无）'}\n\n"
                f"可用证据卡片：\n{evidence_text}\n\n"
                f"请根据以上证据卡片，围绕「{paragraph.topic}」这个主题，撰写一段综述正文（100-200字）。"
                f"每个陈述句末尾必须标注 [证据ID] 引用标记。"
                f"只写这一段的内容，不要写段落标题，不要写其他段落。"
            )

        try:
            return self.llm.chat(system_prompt, user_prompt)
        except Exception as e:
            print(f"⚠️  段落撰写失败（{paragraph.paragraph_id}）: {e}")
            return ""

    def _write_section(
        self,
        section: ReviewSection,
        evidence: list[EvidenceCard],
        review_type: str = "narrative",
        language: str = "en",
        previous_summary: str = "",
        section_index: int = 0,
        total_sections: int = 1,
        feedback: str = "",
    ) -> str:
        """用 LLM 撰写单个章节。
        V25.7: 根据综述模板类型调整写作风格提示。
        V25.9: 支持英文/中文。
        V32.5: 章节类型感知 + 渐进式上下文注入 + 证据-声明矩阵 + 迭代精炼（feedback参数）。
        """
        # B5b: 提示词拼装已抽到 services/review/section_prompts.py
        system_prompt = WRITE_SYSTEM_PROMPT_EN if language.lower() == "en" else WRITE_SYSTEM_PROMPT_ZH
        _, user_prompt = build_write_prompt(
            section,
            evidence,
            review_type=review_type,
            language=language,
            previous_summary=previous_summary,
            feedback=feedback,
            section_index=section_index,
            total_sections=total_sections,
        )

        try:
            return self.llm.chat(system_prompt, user_prompt)
        except LLMError as e:
            print(f"⚠️  章节 {section.title} 撰写失败: {e}")
            # 降级：直接用证据卡片内容拼接
            return "\n".join(f"- {c.content} [{c.evidence_id}]" for c in evidence)

    def _review_section(
        self,
        section: ReviewSection,
        section_text: str,
        evidence: list[EvidenceCard],
        language: str = "en",
    ) -> tuple[float, str]:
        """
        V32.5: 用 LLM 当评审，给章节打分并给出修改建议（迭代精炼 + 评分标准引导）。
        Returns: (score 0-100, revision_suggestions)
        """
        evidence_ids = [c.evidence_id for c in evidence]
        evidence_id_str = ", ".join(evidence_ids[:20])

        if language.lower() == "en":
            system_prompt = (
                "You are a strict academic review reviewer. "
                "Your job is to evaluate the quality of a review section and provide actionable revision suggestions. "
                "Be critical but constructive. Score honestly—do not inflate scores."
            )
            user_prompt = (
                f"## Section Title: {section.title}\n\n"
                f"## Section Text:\n{section_text}\n\n"
                f"## Available Evidence Card IDs: {evidence_id_str}\n\n"
                f"## Evaluation Rubric (score each 0-100, then compute weighted total):\n"
                f"1. Relevance (30%): Is the content directly relevant to the section title? Off-topic content = low score.\n"
                f"2. Evidence Support (30%): Does every claim have evidence support? Are citation markers [ev_xxx] valid and correctly placed? Unsupported claims = low score.\n"
                f"3. Coherence & Logic (20%): Is the content logically organized, flowing smoothly between ideas?\n"
                f"4. Academic Writing (10%): Is the language academic, precise, and well-structured?\n"
                f"5. No Unsupported Speculation (10%): Does the text avoid making claims not backed by the evidence?\n\n"
                f"## Output Format (strictly follow this):\n"
                f"SCORE: [total score 0-100]\n"
                f"ISSUES:\n"
                f"- [specific issue 1]\n"
                f"- [specific issue 2]\n"
                f"SUGGESTIONS:\n"
                f"- [actionable revision suggestion 1]\n"
                f"- [actionable revision suggestion 2]\n"
            )
        else:
            system_prompt = (
                "你是一位严格的学术综述评审专家。"
                "你的任务是评估综述章节的质量，并给出可执行的修改建议。"
                "要批判性但有建设性。诚实地打分——不要虚高分数。"
            )
            user_prompt = (
                f"## 章节标题：{section.title}\n\n"
                f"## 章节正文：\n{section_text}\n\n"
                f"## 可用证据卡片ID：{evidence_id_str}\n\n"
                f"## 评分标准（每项 0-100 分，然后计算加权总分）：\n"
                f"1. 相关性（30%）：内容是否跟章节标题直接相关？跑题内容=低分。\n"
                f"2. 证据支撑（30%）：每个声明是否都有证据支撑？引用标记 [ev_xxx] 是否有效、位置是否正确？无证据支撑的声明=低分。\n"
                f"3. 连贯与逻辑（20%）：内容是否逻辑清晰、观点之间过渡流畅？\n"
                f"4. 学术写作（10%）：语言是否学术、精确、结构良好？\n"
                f"5. 无无依据推测（10%）：文本是否避免做出没有证据支撑的声明？\n\n"
                f"## 输出格式（严格遵守）：\n"
                f"分数：[总分 0-100]\n"
                f"问题：\n"
                f"- [具体问题1]\n"
                f"- [具体问题2]\n"
                f"建议：\n"
                f"- [可执行的修改建议1]\n"
                f"- [可执行的修改建议2]\n"
            )

        try:
            review_result = self.llm.chat(system_prompt, user_prompt)
            # 解析分数
            import re
            score_match = re.search(r'(?:SCORE|分数)[：:]\s*(\d+)', review_result, re.IGNORECASE)
            if score_match:
                score = float(score_match.group(1))
            else:
                # 降级：给一个默认分数
                score = 70.0
            return score, review_result
        except Exception as e:
            print(f"⚠️  评审失败: {e}")
            return 70.0, ""  # 评审失败时给默认分数，不阻塞流程



# Compatibility re-exports: routes/tests historically import these from here.
from .paper_assignment import (  # noqa: E402,F401
    _get_fulltext_doi_map,
    _paper_titles,
    _research_db_path,
    _title_recall_limits,
    assign_papers_to_outline,
    search_and_assign_papers,
)
