"""Citation post-processing mixin for ReviewGenerator."""

from __future__ import annotations

import re

from .models import EvidenceCard, ReviewSentence


class ReviewCitationMixin:
    def _split_and_link(
        self,
        text: str,
        section_id: str,
        evidence: list[EvidenceCard],
        start_seq: int,
    ) -> list[ReviewSentence]:
        """
        将 LLM 输出的章节文本拆分为句子，并关联证据ID。
        解析文本中的 [ev_xxx] 标记作为证据关联。
        """
        import re

        sentences: list[ReviewSentence] = []
        # 按句号/问号/感叹号拆分（保留标点）
        raw_sents = re.split(r'(?<=[。！？.!?])\s*', text)
        valid_evidence_ids = {c.evidence_id for c in evidence}

        for i, raw in enumerate(raw_sents):
            raw = raw.strip()
            if not raw or len(raw) < 5:
                continue

            # 提取句子中的证据ID标记
            found_ids = re.findall(r'\[(ev_[^\]]+)\]', raw)
            # 过滤掉不存在的ID
            linked_ids = [eid for eid in found_ids if eid in valid_evidence_ids]

            # 清理文本中的引用标记（输出时再加回）
            clean_text = re.sub(r'\[ev_[^\]]+\]', '', raw).strip()
            if not clean_text:
                continue

            sentences.append(ReviewSentence(
                sentence_id=f"sent_{section_id}_{start_seq + i}",
                section_id=section_id,
                text=clean_text,
                evidence_ids=linked_ids,
            ))

        return sentences

    # ──────────────────────────────────────────────
    # V25.7: 后处理自动补引用（兜底机制）
    # ──────────────────────────────────────────────

    def _auto_cite_sentences(
        self,
        sentences: list[ReviewSentence],
        section_evidence: list[EvidenceCard],
        min_overlap: int = 2,
    ) -> int:
        """
        对无引用的句子，从同章节证据卡片中自动匹配最相关的，补上引用标记。

        匹配策略：字符级 2-gram 关键词重叠（对中英文均适用，无需分词）。
        阈值：至少 min_overlap 个 2-gram 重叠才补，否则保持无引用（会被校验拒绝）。

        Args:
            sentences: 本章节的句子列表（会原地修改 evidence_ids 和 verification_note）
            section_evidence: 本章节可用的证据卡片列表
            min_overlap: 最小关键词重叠数阈值，默认 2

        Returns:
            自动补引用的句子数量
        """
        if not sentences or not section_evidence:
            return 0

        # 预计算每个证据卡片的 2-gram 集合（content + original_quote）
        evidence_ngrams: list[tuple[str, set[str]]] = []
        for card in section_evidence:
            text = card.content or ""
            if card.original_quote:
                text += " " + card.original_quote
            ngrams = self._extract_2grams(text)
            if ngrams:
                evidence_ngrams.append((card.evidence_id, ngrams))

        if not evidence_ngrams:
            return 0

        auto_cited = 0
        for sent in sentences:
            # 只处理无引用的句子
            if sent.evidence_ids:
                continue

            sent_ngrams = self._extract_2grams(sent.text)
            if not sent_ngrams:
                continue

            # 找重叠最多的证据卡片
            best_eid = None
            best_overlap = 0
            for eid, e_ngrams in evidence_ngrams:
                overlap = len(sent_ngrams & e_ngrams)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_eid = eid

            # 达到阈值才补
            if best_eid and best_overlap >= min_overlap:
                sent.evidence_ids = [best_eid]
                sent.verification_note = f"自动补引用: {best_eid}（关键词重叠数={best_overlap}，建议人工复核）"
                auto_cited += 1

        return auto_cited

    @staticmethod
    def _extract_2grams(text: str) -> set[str]:
        """
        从文本中提取字符级 2-gram 集合（对中英文均适用，无需分词）。
        转小写，去除标点和空白，只保留字母、数字、中文字符。

        例如："STAT1在IFN-gamma刺激下被磷酸化" → {"st","ta","a1","1在","在i","if","fn","n-",...}
        """
        import re

        if not text:
            return set()

        # 转小写，只保留字母、数字、中文字符
        cleaned = re.sub(r'[^\w\u4e00-\u9fff]', '', text.lower())
        if len(cleaned) < 2:
            return set()

        # 提取所有连续2个字符的组合
        return {cleaned[i:i+2] for i in range(len(cleaned) - 1)}
