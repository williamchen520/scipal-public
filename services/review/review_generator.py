"""
V25.0 - 综述生成主流程（ReviewGenerator）。

串联完整流水线：
  用户主题 → 检索 → 证据抽取 → 大纲生成 → 撰写 → 引用校验 → Markdown 输出

V25.0 范围：
- 检索：复用 UnifiedRetriever
- 证据抽取：EvidenceExtractor（LLM）
- 大纲：简单规则生成（按证据类型/章节分组），或接受用户传入大纲
- 撰写：LLM 基于证据卡片写段落，严格限制只能用证据内容
- 校验：CitationVerifier（确定性 + 可选 LLM 深度校验）
- 输出：Markdown（仅含已验证句子 + 参考文献列表）

用法:
    generator = ReviewGenerator(llm_client, retriever)
    output = generator.generate(topic="STAT1 干扰素调控", max_papers=20)
    print(output.markdown)
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Optional

from .citation_formatter import PaperMetadata, build_metadata_from_db_row, format_citation, format_citation_list, get_missing_fields_report, get_supported_styles, metadata_to_csl_json
from .citation_verifier import CitationVerifier
from .evidence_extractor import EvidenceExtractor
from .query_builder import build_section_query, is_paper_relevant, rank_papers
from . import title_recall
from .section_loop import write_section_loop
from .section_prompts import build_write_prompt
from .llm_client import LLMClient, LLMError
from .review_citation import ReviewCitationMixin
from .review_draft import ReviewDraftMixin
from .review_render import ReviewRenderMixin
from .models import (
    EvidenceCard,
    EvidenceType,
    ReviewDraft,
    ReviewOutput,
    ReviewOutline,
    ReviewParagraph,
    ReviewSection,
    ReviewSentence,
    SentenceStatus,
)


# ──────────────────────────────────────────────
# 撰写 Agent Prompt（V25.9: 英文默认，保留中文向后兼容）
# ──────────────────────────────────────────────

from .review_prompts import WRITE_SYSTEM_PROMPT, WRITE_SYSTEM_PROMPT_EN, WRITE_SYSTEM_PROMPT_ZH



# ──────────────────────────────────────────────
# 综述生成器
# ──────────────────────────────────────────────

class ReviewGenerator(ReviewDraftMixin, ReviewCitationMixin, ReviewRenderMixin):
    """
    综述生成主流程控制器。

    Args:
        llm_client: LLMClient 实例
        retriever: UnifiedRetriever 实例（用于检索相关文献）
        max_evidence_per_paper: 每篇论文最多保留的证据数，默认 5
        use_llm_verification: 是否启用 LLM 深度校验，默认 False（V25.0 先用确定性校验）
    """

    def __init__(
        self,
        llm_client: LLMClient,
        retriever=None,
        max_evidence_per_paper: int = 5,
        use_llm_verification: bool = False,
        db_path: Optional[str] = None,
    ):
        self.llm = llm_client
        self.retriever = retriever
        self.max_evidence_per_paper = max_evidence_per_paper
        self.use_llm_verification = use_llm_verification
        self.db_path = db_path  # V25.7: 保存数据库路径，用于查询论文元数据做参考文献格式化
        # V25.4 优化：轻量任务（证据抽取/关系抽取/冲突识别）用轻量模型
        # （从环境变量 SCIPAL_LLM_LIGHT_MODEL 读取，本地默认 qwen2.5:3b，云端默认 qwen-turbo）
        # V33.9: 重模型改用 7b Q4_K_M 量化版（8GB显存可跑），只有大纲生成和撰写保留重模型
        from .llm_client import create_llm_client
        self._light_llm = create_llm_client(light=True, timeout=300, max_retries=2)
        self.extractor = EvidenceExtractor(self._light_llm)
        self.verifier = CitationVerifier(self._light_llm if use_llm_verification else None)
        # V31.22: 大纲生成也改成用 light_llm（3B），速度快
        from .outline_generator import OutlineGenerator
        self.outline_generator = OutlineGenerator(self._light_llm, db_path=db_path)
        # V25.3: 关系抽取器 + 冲突识别 Agent —— 用7b
        from .relation_extractor import RelationExtractor
        from .conflict_detector import ConflictDetector
        # V31.81: 关系抽取不调用 LLM，只用关键词粗筛（196个证据卡片调用LLM会卡住几小时）
        self.relation_extractor = RelationExtractor(None)
        # V31.81: 冲突检测也不调用 LLM，避免卡住
        self.conflict_detector = ConflictDetector(None)
        # V25.6: 保存最后一次生成的 draft 和 evidence_cards，用于前端点击溯源
        self._last_draft: Optional[ReviewDraft] = None
        self._last_evidence_cards: list[EvidenceCard] = []
        # V25.7: 自动补引用计数器（每次 generate 开始时清零）
        self._auto_cite_count: int = 0
        # V33.4: 证据不足 fallback —— 记录最后一次生成中证据不足的章节
        self._insufficient_evidence_sections: list[str] = []

    def get_insufficient_evidence_sections(self) -> list[str]:
        """V33.4: 获取最后一次生成中证据不足的章节列表。

        Returns:
            证据不足的章节标题列表。如果所有章节证据充足，返回空列表。
        """
        return self._insufficient_evidence_sections.copy()

    def _check_cancel(self, task_id: Optional[str], progress: Optional[str] = None) -> None:
        """C-2: 阶段间取消检查 + 粗粒度进度上报。

        只在**阶段之间**生效：检索、证据抽取、大纲、撰写、校验这几个边界。
        阶段内部（尤其是 `_write_draft` 的 LLM 长调用、`_retrieve` 的向量检索）
        是原子的，**无法中途打断** —— 取消请求会在下一个边界点被观察到。
        """
        if not task_id:
            return
        from .task_manager import task_manager
        if progress:
            task_manager.update_progress(task_id, progress)
        if task_manager.is_cancelled(task_id):
            raise Exception("Task cancelled by user")

    def generate(
        self,
        topic: str,
        max_papers: int = 20,
        outline: Optional[ReviewOutline] = None,
        citation_style: str = "apa",
        review_type: str = "narrative",
        custom_outline: Optional[dict] = None,
        language: str = "en",
        include_abstracts: bool = True,
        selected_paper_ids: Optional[list[str]] = None,
        excluded_paper_ids: Optional[list[str]] = None,
        task_id: Optional[str] = None,
    ) -> ReviewOutput:
        """
        生成综述。

        Args:
            topic: 综述主题
            max_papers: 最多检索的论文数
            outline: 可选用户自定义大纲（ReviewOutline 对象）；不传则自动生成
            citation_style: 参考文献格式（apa / nature / vancouver），默认 apa
            review_type: 综述模板类型（V25.7）：
                - "narrative": 叙事型（默认，按逻辑线索组织）
                - "comparative": 实验对比型（按方法/模型对比）
                - "systematic": 系统综述型（严格方法学结构）
            custom_outline: V25.8 用户自定义段落级大纲（JSON 格式），优先级高于 outline 和自动生成。
                格式：{"sections": [{"title": "...", "paragraphs": [{"topic": "...", "assigned_paper_ids": [...]}]}]}
            language: V25.9: 综述生成语言，"en"（默认，英文）或 "zh"（中文）
            include_abstracts: V26.0: 是否包含摘要库的论文，默认 True
            selected_paper_ids: V26.0: 用户选定的论文 ID 列表，如果指定则只用这些论文
            excluded_paper_ids: V26.0: 用户要剔除的论文 ID 列表

            task_id: V33.17 C-2: 传入 review 任务 id 时，会在**阶段之间**检查取消并上报进度。

        Returns:
            ReviewOutput（含 Markdown 全文、参考文献、统计、警告）

        取消语义（如实说明，不要误以为可随时中断）：
            检查点只有 5 个 —— 检索前 / 证据抽取前 / 大纲前 / 撰写前 / 校验前。
            · 检索、证据抽取、大纲、撰写、校验**各自内部不可中断**；
            · 最耗时的 `_write_draft`（LLM 逐段撰写）一旦开始，取消要等它整段跑完
              才会在「校验前」被观察到；
            · 因此取消的实效粒度是「阶段级」，不是「句子级」。
        """
        warnings: list[str] = []

        # V31.83: 如果 custom_outline 里已经有证据卡片（按大纲搜索并分配时保存的），就直接用
        custom_evidence_cards = None
        print(f"🔍 V31.83 调试: custom_outline is None? {custom_outline is None}")
        if custom_outline is not None:
            print(f"🔍 V31.83 调试: custom_outline type? {type(custom_outline)}")
            if isinstance(custom_outline, dict):
                print(f"🔍 V31.83 调试: custom_outline keys? {list(custom_outline.keys())}")
                raw_evidence = custom_outline.get("evidence_cards")
                print(f"🔍 V31.83 调试: evidence_cards is None? {raw_evidence is None}")
                if raw_evidence is not None:
                    print(f"🔍 V31.83 调试: evidence_cards type? {type(raw_evidence)}")
                    if isinstance(raw_evidence, list):
                        print(f"🔍 V31.83 调试: evidence_cards length? {len(raw_evidence)}")
                        if len(raw_evidence) > 0:
                            print(f"🔍 V31.83 调试: first evidence keys? {list(raw_evidence[0].keys()) if isinstance(raw_evidence[0], dict) else type(raw_evidence[0])}")
                if raw_evidence and isinstance(raw_evidence, list) and len(raw_evidence) > 0:
                    from .models import EvidenceCard
                    custom_evidence_cards = []
                    failed_count = 0
                    for ev_dict in raw_evidence:
                        try:
                            card = EvidenceCard(**ev_dict)
                            custom_evidence_cards.append(card)
                        except Exception as e:
                            failed_count += 1
                            if failed_count <= 3:
                                print(f"⚠️  V31.83 调试: EvidenceCard 转换失败: {e}, ev_dict keys: {list(ev_dict.keys()) if isinstance(ev_dict, dict) else type(ev_dict)}")
                    print(f"🔍 V31.83 调试: 转换成功 {len(custom_evidence_cards)} 条，失败 {failed_count} 条")
                    if custom_evidence_cards:
                        print(f"📋 V31.83: 使用 custom_outline 里的证据卡片，共 {len(custom_evidence_cards)} 条（按章节主题搜索的，内容更相关）")
                        warnings.append(f"📋 使用按大纲搜索分配的证据卡片：{len(custom_evidence_cards)} 条（按章节主题搜索，内容更相关）")

        # ── Step 1: 检索 ──
        self._check_cancel(task_id, "检索文献...")
        if custom_evidence_cards is not None:
            # V31.83: 已经有证据卡片了，跳过检索
            paragraphs = []
            warnings.append(f"⏭️  跳过检索（使用按大纲搜索分配的证据卡片）")
        else:
            paragraphs = self._retrieve(
                topic,
                max_papers,
                include_abstracts=include_abstracts,
                selected_paper_ids=selected_paper_ids,
                excluded_paper_ids=excluded_paper_ids,
            )
            if not paragraphs:
                return ReviewOutput(
                    topic=topic,
                    markdown=f"# {topic}\n\n未检索到相关文献。",
                    stats={"total_sentences": 0, "total_evidence": 0},
                    warnings=["未检索到相关文献，请调整主题或增加 max_papers。"],
                )
            warnings.append(f"📚 检索到 {len(paragraphs)} 个相关段落。")

        # ── Step 2: 证据抽取 ──
        self._check_cancel(task_id, "抽取证据...")
        if custom_evidence_cards is not None:
            # V31.83: 已经有证据卡片了，跳过证据抽取
            evidence_cards = custom_evidence_cards
        else:
            evidence_cards = self.extractor.extract_from_paragraphs(paragraphs, topic=topic, language=language)
            # 每篇论文限数
            evidence_cards = self._limit_evidence_per_paper(evidence_cards)
            if not evidence_cards:
                return ReviewOutput(
                    topic=topic,
                    markdown=f"# {topic}\n\n未能从文献中抽取到有效证据。",
                    stats={"total_sentences": 0, "total_evidence": 0},
                    warnings=["证据抽取失败或所有段落均为 boilerplate。"],
                )
        warnings.append(f"🔍 共 {len(evidence_cards)} 条证据卡片。")

        # ── Step 2.5: 全局短 ID 重映射（V25.1）──
        # V31.83: 如果用的是 custom_outline 里的证据卡片，就不要做短 ID 重映射
        # 因为 custom_outline 里的 assigned_evidence_ids 还是原来的长 ID
        if custom_evidence_cards is None:
            # 将长 evidence_id 统一映射为 ev_001, ev_002... 短序号，
            # 避免 paper_id 含空格/特殊字符导致 LLM 引用标记解析失败。
            evidence_cards = self._remap_to_short_ids(evidence_cards)
        evidence_dict = {c.evidence_id: c for c in evidence_cards}

        # ── Step 3: 大纲（V25.2: LLM 大纲生成；V25.8: 支持用户自定义段落级大纲）──
        self._check_cancel(task_id, "生成大纲...")
        if custom_outline is not None:
            # V25.8: 用户自定义段落级大纲（优先级最高）
            from .outline_generator import OutlineGenerator
            outline = OutlineGenerator.from_custom_json(topic, custom_outline, evidence_cards=evidence_cards)
            total_paragraphs = sum(len(s.paragraphs) for s in outline.sections)
            warnings.append(f"📝 使用用户自定义大纲：{len(outline.sections)} 个章节，{total_paragraphs} 个段落。")
        elif outline is None:
            # 自动生成大纲（LLM 优先，规则版 fallback）
            outline = self.outline_generator.generate(topic, evidence_cards, use_communities=True, review_type=review_type, language=language)
            total_paragraphs = sum(len(s.paragraphs) for s in outline.sections)
            warnings.append(f"📋 大纲包含 {len(outline.sections)} 个章节，{total_paragraphs} 个段落。")
        else:
            total_paragraphs = sum(len(s.paragraphs) for s in outline.sections)
            warnings.append(f"📋 使用传入大纲：{len(outline.sections)} 个章节，{total_paragraphs} 个段落。")

        # ── Step 3.5: 关系抽取 + 冲突识别（V25.3）──
        # V31.82: 综述生成不需要关系抽取和冲突检测！这些是问答/分析功能用的，综述跳过！
        # 关系抽取会对196个证据卡片做O(n²)的LLM判定，卡住几小时，完全没必要！
        print(f"⏭️  V31.82: 综述生成跳过关系抽取和冲突检测（这些是问答功能用的）")
        relations = []
        conflicts = []

        # V31.82: 只写正文，不做冲突检测（并行处理也不需要了）
        self._check_cancel(task_id, "撰写正文...")
        self._auto_cite_count = 0  # V25.7: 每次生成前清零自动补引用计数器
        draft = self._write_draft(topic, outline, evidence_dict, review_type=review_type, language=language)

        warnings.append(f"✍️  撰写完成，共 {len(draft.sentences)} 句。")
        if self._auto_cite_count > 0:
            warnings.append(f"🔧 后处理自动补引用 {self._auto_cite_count} 句（从同章节证据中关键词匹配，建议人工复核）。")

        # ── Step 5: 校验 ──
        self._check_cancel(task_id, "校验引用...")
        draft, verify_warnings = self.verifier.verify(draft, use_llm=self.use_llm_verification)
        warnings.extend(verify_warnings)

        # ── Step 6: 输出 Markdown（V25.3: 含研究争议章节）──
        # V25.7: 查询论文元数据，用于多格式参考文献格式化
        paper_metadata_map = self._fetch_paper_metadata(evidence_cards)
        markdown = self._render_markdown(topic, draft, evidence_dict, conflicts=conflicts, paper_metadata_map=paper_metadata_map, citation_style=citation_style, language=language)
        references = self._build_references(evidence_cards, paper_metadata_map=paper_metadata_map, citation_style=citation_style)

        # V25.6: 保存最后一次的 draft 和 evidence_cards，用于前端点击溯源
        self._last_draft = draft
        self._last_evidence_cards = evidence_cards

        return ReviewOutput(
            topic=topic,
            markdown=markdown,
            references=references,
            stats=draft.stats(),
            warnings=warnings,
            relations=[r.model_dump() for r in relations],
            conflicts=[c.model_dump() for c in conflicts],
            review_type=review_type,
        )

    def generate_outline(
        self,
        topic: str,
        max_papers: int = 20,
        review_type: str = "narrative",
        custom_outline: Optional[dict] = None,
        language: str = "en",
        include_abstracts: bool = True,
        selected_paper_ids: Optional[list[str]] = None,
        excluded_paper_ids: Optional[list[str]] = None,
        task_id: Optional[str] = None,  # V26.3: 用于取消任务
    ) -> dict:
        """
        V25.8: 只生成段落级大纲（不撰写），供用户查看和修改。
        V25.9: 支持 language 参数（默认英文）。
        V26.0: 支持包含摘要库、用户选定或剔除论文。
        V26.3: 支持 task_id 参数，可取消任务。

        返回包含：
        - topic: 综述主题
        - outline: 段落级大纲（章节→段落→每段主题→每段分配的论文/证据）
        - evidence_cards: 证据卡片列表（供用户了解每篇论文写了什么）
        - papers: 涉及的论文列表（paper_id + title）
        - stats: 统计信息
        """
        # ── Step 1: 检索 ──
        if task_id:
            from .task_manager import task_manager
            task_manager.update_progress(task_id, "检索文献中...")
        paragraphs = self._retrieve(
            topic,
            max_papers,
            include_abstracts=include_abstracts,
            selected_paper_ids=selected_paper_ids,
            excluded_paper_ids=excluded_paper_ids,
        )

        # V26.3: 检查是否被取消
        if task_id:
            from .task_manager import task_manager
            if task_manager.is_cancelled(task_id):
                raise Exception("Task cancelled by user")

        if not paragraphs:
            return {
                "topic": topic,
                "outline": {"sections": []},
                "evidence_cards": [],
                "papers": [],
                "stats": {"total_paragraphs": 0, "total_evidence": 0, "total_papers": 0},
                "warnings": ["未检索到相关文献。"],
            }

        # ── Step 2: 证据抽取 ──
        if task_id:
            from .task_manager import task_manager
            task_manager.update_progress(task_id, "抽取证据中...")
        evidence_cards = self.extractor.extract_from_paragraphs(paragraphs, topic=topic, language=language)
        evidence_cards = self._limit_evidence_per_paper(evidence_cards)

        # V26.3: 检查是否被取消
        if task_id:
            from .task_manager import task_manager
            if task_manager.is_cancelled(task_id):
                raise Exception("Task cancelled by user")

        if not evidence_cards:
            return {
                "topic": topic,
                "outline": {"sections": []},
                "evidence_cards": [],
                "papers": [],
                "stats": {"total_paragraphs": len(paragraphs), "total_evidence": 0, "total_papers": 0},
                "warnings": ["证据抽取失败或所有段落均为 boilerplate。"],
            }

        # 短 ID 重映射
        evidence_cards = self._remap_to_short_ids(evidence_cards)
        evidence_dict = {c.evidence_id: c for c in evidence_cards}

        # ── Step 3: 生成大纲 ──
        # V26.3: 检查是否被取消
        if task_id:
            from .task_manager import task_manager
            task_manager.update_progress(task_id, "生成大纲中...")
            if task_manager.is_cancelled(task_id):
                raise Exception("Task cancelled by user")

        if custom_outline is not None:
            from .outline_generator import OutlineGenerator
            outline = OutlineGenerator.from_custom_json(topic, custom_outline, evidence_cards=evidence_cards)
        else:
            print(f"📝 开始生成大纲（规则版）...")
            outline = self.outline_generator.generate(topic, evidence_cards, use_communities=True, review_type=review_type, language=language)
            print(f"✅ 大纲生成完成：{len(outline.sections)} 个章节")

        print(f"📚 开始构建论文列表...")
        # V26.1: 构建论文列表 - 从 paragraphs 里提取所有论文，不只是 evidence_cards 里的
        paper_map = {}
        for p in paragraphs:
            pid = p.get("paper_id", "")
            if not pid:
                continue
            src = p.get("source", "full_text")
            if pid not in paper_map:
                paper_map[pid] = {
                    "paper_id": pid,
                    "title": p.get("paper_title", pid),
                    "source": src,
                    "evidence_count": 0,
                    "fulltext_evidence_count": 0,  # V33.17: 全文证据数
                    "abstract_evidence_count": 0,  # V33.17: 摘要证据数
                }
            elif src == "full_text":
                # V33.17: 同一篇论文既有全文段落又有摘要时，论文级 source 标全文
                paper_map[pid]["source"] = "full_text"
        # 统计每篇论文的证据数量（V33.17: 区分全文/摘要）
        for c in evidence_cards:
            if c.paper_id in paper_map:
                paper_map[c.paper_id]["evidence_count"] += 1
                if getattr(c, "source_type", "full_text") == "abstract":
                    paper_map[c.paper_id]["abstract_evidence_count"] += 1
                else:
                    paper_map[c.paper_id]["fulltext_evidence_count"] += 1
        papers = list(paper_map.values())
        paper_ids = list(paper_map.keys())  # V26.1: 保留 paper_ids 变量，兼容后面的代码

        # 构建可序列化的大纲（包含段落主题和分配的论文）
        outline_json = {
            "sections": []
        }
        for sec in outline.sections:
            sec_data = {
                "section_id": sec.section_id,
                "title": sec.title,
                "description": sec.description,
                "assigned_paper_ids": sec.assigned_paper_ids,
                "paragraphs": [],
            }
            for para in sec.paragraphs:
                para_data = {
                    "paragraph_id": para.paragraph_id,
                    "topic": para.topic,
                    "description": para.description,
                    "assigned_paper_ids": para.assigned_paper_ids,
                    "assigned_evidence_ids": para.assigned_evidence_ids,
                }
                sec_data["paragraphs"].append(para_data)
            outline_json["sections"].append(sec_data)

        total_paragraphs = sum(len(s.paragraphs) for s in outline.sections)

        print(f"✅ 大纲生成全部完成：{len(outline.sections)} 个章节，{total_paragraphs} 个段落，{len(paper_map)} 篇论文")

        return {
            "topic": topic,
            "review_type": review_type,
            "outline": outline_json,
            "evidence_cards": [
                {
                    "evidence_id": c.evidence_id,
                    "paper_id": c.paper_id,
                    "content": c.content,
                    "evidence_type": c.evidence_type.value,
                    "section_l1": c.section_l1,
                }
                for c in evidence_cards
            ],
            "papers": papers,
            "stats": {
                "total_paragraphs_retrieved": len(paragraphs),
                "total_evidence": len(evidence_cards),
                "total_papers": len(paper_ids),
                "total_sections": len(outline.sections),
                "total_paragraphs": total_paragraphs,
            },
            "warnings": [
                f"检索到 {len(paragraphs)} 个段落，抽取到 {len(evidence_cards)} 条证据，涉及 {len(paper_ids)} 篇论文。",
                f"生成大纲：{len(outline.sections)} 个章节，{total_paragraphs} 个段落。",
            ],
        }

    # ──────────────────────────────────────────
    # 内部步骤
    # ──────────────────────────────────────────

    def _retrieve(
        self,
        topic: str,
        max_papers: int,
        include_abstracts: bool = True,
        selected_paper_ids: Optional[list[str]] = None,
        excluded_paper_ids: Optional[list[str]] = None,
    ) -> list[dict]:
        """调用检索层获取相关段落。

        V26.0: 支持同时检索全文库和摘要库，支持用户选定或剔除论文。
        """
        if self.retriever is None:
            return []

        try:
            # V31.71: 回退到旧的 self.retriever.retrieve(...)，检索层不改，只改数据层
            result = self.retriever.retrieve(
                query=topic,
                top_paragraphs=max_papers,
                top_figures=0,
            )
            paragraphs = []
            for p in result.get("paragraphs", []):
                paper_id = p.get("paper_id", "")

                # V26.0: 如果用户指定了要剔除的论文，跳过
                if excluded_paper_ids and paper_id in excluded_paper_ids:
                    continue

                # V26.0: 如果用户指定了要选定的论文，只保留这些
                if selected_paper_ids and paper_id not in selected_paper_ids:
                    continue

                paragraphs.append({
                    "para_id": p.get("para_id", ""),
                    "paper_id": paper_id,
                    "text": p.get("text", ""),
                    "section_l1": p.get("section_l1", ""),
                    "page": p.get("page", 0),
                    "paper_title": p.get("paper_title", ""),
                    "source": p.get("source", "full_text"),  # V26.0: 标注来源
                    "source_type": "full_text",  # V33.17: 证据抽取层读这个字段
                })

            # V26.0: 如果需要包含摘要库，也检索摘要库
            # V33.17: 摘要回退 + DOI 去重——摘要命中若对应全文库论文，归到全文 paper_id 名下
            if include_abstracts and hasattr(self.retriever, 'abstract_searcher'):
                try:
                    abstract_results = self.retriever.abstract_searcher.search(
                        topic, top_k=max_papers
                    )
                    doi_map = _get_fulltext_doi_map()  # V33.17
                    for a in abstract_results:
                        # V26.0: 摘要库返回的是 pmid，不是 paper_id
                        paper_id = a.get("paper_id", "") or a.get("pmid", "")

                        # V33.17: DOI 去重——全文库里有同一篇论文时，
                        # 摘要证据合并到全文 paper_id 名下（一篇论文只有一个身份）
                        doi = (a.get("doi", "") or "").strip().lower()
                        if doi and doi in doi_map:
                            paper_id = doi_map[doi]

                        # V26.0: 如果用户指定了要剔除的论文，跳过
                        if excluded_paper_ids and paper_id in excluded_paper_ids:
                            continue

                        # V26.0: 如果用户指定了要选定的论文，只保留这些
                        if selected_paper_ids and paper_id not in selected_paper_ids:
                            continue

                        # V33.17: 避免同一篇论文的摘要重复添加
                        para_id = f"abstract_{a.get('pmid', '') or paper_id}"
                        if any(p["paper_id"] == paper_id and p["para_id"] == para_id for p in paragraphs):
                            continue

                        paragraphs.append({
                            "para_id": para_id,
                            "paper_id": paper_id,
                            "text": a.get("abstract", ""),
                            "section_l1": "Abstract",
                            "page": 0,
                            "paper_title": a.get("title", ""),
                            "source": "abstract",  # V26.0: 标注是摘要
                            "source_type": "abstract",  # V33.17: 证据抽取层读这个字段
                        })
                except Exception as e:
                    print(f"⚠️  摘要库检索失败: {e}")

            print(f"📚 检索到 {len(paragraphs)} 个相关段落")
            return paragraphs
        except Exception as e:
            print(f"⚠️  检索失败: {e}")
            return []

    def _limit_evidence_per_paper(self, cards: list[EvidenceCard]) -> list[EvidenceCard]:
        """每篇论文最多保留 max_evidence_per_paper 条证据（按置信度排序）。"""
        by_paper: dict[str, list[EvidenceCard]] = defaultdict(list)
        for c in cards:
            by_paper[c.paper_id].append(c)

        result = []
        for paper_id, paper_cards in by_paper.items():
            paper_cards.sort(key=lambda c: c.confidence, reverse=True)
            result.extend(paper_cards[:self.max_evidence_per_paper])
        return result

    @staticmethod
    def _remap_to_short_ids(cards: list[EvidenceCard]) -> list[EvidenceCard]:
        """V25.1: 将长 evidence_id 全局重映射为 ev_001, ev_002... 短序号。

        原因：paper_id 可能含空格/特殊字符（如文件名直接当 ID），
        导致 evidence_id 超长且 LLM 撰写时引用标记容易截断/格式错乱，
        校验阶段匹配不上而被误拒。重映射后：
        - LLM 看到的证据 ID 是短序号，写 [ev_001] 不会出错
        - paper_id / para_id 字段保留原始值，用于溯源
        - 输出参考文献时从 card 字段查，不依赖 evidence_id
        """
        for i, card in enumerate(cards):
            card.evidence_id = f"ev_{i + 1:03d}"
        return cards

    def _generate_simple_outline(
        self,
        topic: str,
        evidence_cards: list[EvidenceCard],
    ) -> ReviewOutline:
        """
        生成简单大纲（V25.0 规则版，V25.1 升级为 LLM 大纲生成）。
        按证据类型分组为章节：背景 → 机制 → 事实/方法 → 局限性。
        """
        # 按证据类型分组
        type_groups: dict[EvidenceType, list[EvidenceCard]] = defaultdict(list)
        for c in evidence_cards:
            type_groups[c.evidence_type].append(c)

        sections = []
        order = 0

        # 背景
        if type_groups.get(EvidenceType.BACKGROUND):
            sections.append(ReviewSection(
                section_id=f"sec_{order:02d}",
                title="研究背景",
                description="领域背景与研究意义",
                order=order,
                assigned_evidence_ids=[c.evidence_id for c in type_groups[EvidenceType.BACKGROUND]],
            ))
            order += 1

        # 机制
        if type_groups.get(EvidenceType.MECHANISM):
            sections.append(ReviewSection(
                section_id=f"sec_{order:02d}",
                title="分子机制",
                description="关键分子机制与信号通路",
                order=order,
                assigned_evidence_ids=[c.evidence_id for c in type_groups[EvidenceType.MECHANISM]],
            ))
            order += 1

        # 实验事实
        fact_cards = type_groups.get(EvidenceType.FACT, []) + type_groups.get(EvidenceType.CLAIM, [])
        if fact_cards:
            sections.append(ReviewSection(
                section_id=f"sec_{order:02d}",
                title="实验证据",
                description="关键实验结果与数据",
                order=order,
                assigned_evidence_ids=[c.evidence_id for c in fact_cards],
            ))
            order += 1

        # 方法
        if type_groups.get(EvidenceType.METHOD):
            sections.append(ReviewSection(
                section_id=f"sec_{order:02d}",
                title="研究方法",
                description="主要实验方法与模型系统",
                order=order,
                assigned_evidence_ids=[c.evidence_id for c in type_groups[EvidenceType.METHOD]],
            ))
            order += 1

        # 局限性
        if type_groups.get(EvidenceType.LIMITATION):
            sections.append(ReviewSection(
                section_id=f"sec_{order:02d}",
                title="研究局限与展望",
                description="现有研究的局限性与未来方向",
                order=order,
                assigned_evidence_ids=[c.evidence_id for c in type_groups[EvidenceType.LIMITATION]],
            ))
            order += 1

        # 如果没有任何分组（所有证据都是 fact），创建一个默认章节
        if not sections:
            sections.append(ReviewSection(
                section_id="sec_00",
                title="综述",
                description=f"关于 {topic} 的文献综述",
                order=0,
                assigned_evidence_ids=[c.evidence_id for c in evidence_cards],
            ))

        return ReviewOutline(
            topic=topic,
            sections=sections,
            total_papers=len(set(c.paper_id for c in evidence_cards)),
            total_evidence=len(evidence_cards),
        )


# Compatibility re-exports: routes/tests historically import these from here.
from .paper_assignment import (  # noqa: E402,F401
    _get_fulltext_doi_map,
    _paper_titles,
    _research_db_path,
    _title_recall_limits,
    assign_papers_to_outline,
    search_and_assign_papers,
)
