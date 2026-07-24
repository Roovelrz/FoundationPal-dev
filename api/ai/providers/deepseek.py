import os
import json
from typing import Any
from openai import OpenAI

from .base import BaseProvider, AIResult
from ai.validators import (
    validate_planner_output, validate_writer_output,
    validate_reviser_output, validate_formatter_output, SchemaError,
)
from .util import summarize_file_refs
from ai.context_budget import apply_context_budget
from ai.diff_engine import diff_texts
from ai.synthetic_eval import SyntheticEvalRequest

NSFC_WRITER_SYSTEM = """你是一位NSFC基金申请书撰写专家，有多年成功申请经验。请撰写专业严谨的申请书内容。

写作准则:
1. 客观严谨，用事实和数据说话。多用动宾结构:揭示...机理、阐明...机制、建立...模型、突破...瓶颈
2. 避免口语化和夸大表述:禁止"填补空白""国际领先""世界首次""首创"
3. 立项依据从宏观到微观层层递进:研究领域->研究对象->科学问题->问题剖析->解决思路
4. 参考文献以近5年为主，CNS等权威期刊优先
5. 研究内容3-4项为宜，各项相互支撑、环环相扣
6. 关键科学问题2条左右，区分科学问题和技术问题
7. 全文人称统一用"本项目"，不用"我们"
8. 输出纯Markdown文本，不要JSON包裹"""

NSFC_REVISER_SYSTEM = """你是一位NSFC基金申请评审专家。根据修改要求和评审标准修订申请书。

评审标准:
1. 科学问题是否聚焦且重要？是否区别于技术/工程问题？
2. 创新性是否实质，而非简单工具套用？
3. 立项依据到研究方案的逻辑链是否完整？
4. 研究方案是否具体可操作？
5. 是否存在夸大表述或遗漏关键前人工作？

常见扣分点:科学问题太大太空、创新点过多、研究方案不具体、逻辑链断裂
针对标准逐条审查，直接输出修订后文本。"""

NSFC_FORMATTER_SYSTEM = """你是一位NSFC申请书排版专家。按NSFC规范排版为完整文档。

格式要求:
- 正文不超过30页(建议20页以内)
- 参考文献约30条，编号[1][2]...
- 章节标题用##标记，子标题用###标记"""


class DeepSeekProvider(BaseProvider):
    def __init__(self):
        api_key = os.getenv("LLM_API_KEY", "")
        if not api_key:
            raise RuntimeError("LLM_API_KEY not set")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
        self.model = os.getenv("LLM_MODEL", "deepseek-chat")
        self.client = OpenAI(api_key=api_key, base_url=self.base_url)
        self.last_usage = {'prompt_tokens': 0, 'completion_tokens': 0, 'cached_tokens': 0, 'total_tokens': 0}

    def _call(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            max_tokens=max_tokens, temperature=0.3,
        )
        usage = resp.usage
        details = getattr(usage, 'prompt_tokens_details', None)
        self.last_usage = {
            'prompt_tokens': getattr(usage, 'prompt_tokens', 0) or 0,
            'completion_tokens': getattr(usage, 'completion_tokens', 0) or 0,
            'cached_tokens': getattr(details, 'cached_tokens', 0) or 0,
            'total_tokens': getattr(usage, 'total_tokens', 0) or 0,
        }
        return resp.choices[0].message.content or ""

    def generate_synthetic_eval_case(self, request: SyntheticEvalRequest) -> str:
        system = (
            '你是国家自然科学基金申请人评测集生成器。只根据给定证据生成一个可验证问题。'
            '输出单个 JSON 对象，不要 Markdown。'
            '字段必须为 usable、query、reference_answer、query_type。'
            '问题不得复制证据原句，答案必须简洁且只能由证据支持。'
            '必须保留证据中的年份、金额、期限、资格和否定条件。'
            '若证据语义不完整或无法独立回答，返回 usable 为 false。'
        )
        user = (
            f'资料类型：{request.source_type}\n'
            f'指定问题类型：{request.query_type}\n'
            f'证据：\n{request.evidence}'
        )
        return self._call(system, user, max_tokens=600)

    def judge_rag_context(self, *, query: str, reference_answer: str, candidates: list[dict]) -> str:
        context = '\n\n'.join(
            f'[chunk_id={item["chunk_id"]}]\n{item["text"]}' for item in candidates[:5]
        )
        system = (
            '你是 RAG 检索评测裁判。只依据给定上下文判断其能否完整支持参考答案。'
            '输出单个 JSON 对象，字段为 answerable_from_context、supporting_chunk_ids、coverage、missing_information、irrelevant_chunk_ids。'
            'coverage 只能是 complete、partial 或 none。'
        )
        user = f'问题：{query}\n参考答案：{reference_answer}\n上下文：\n{context}'
        return self._call(system, user, max_tokens=500)

    def plan(self, *, grant_url: str | None, text_spec: str | None) -> dict:
        source = grant_url or text_spec or "N/A"
        system = (
            "你是一位NSFC基金申请规划专家。根据研究方向，为4个固定章节生成引导性问题。\n"
            "必须使用以下固定id:\n"
            '  "lixiangyiju" -> "(一)立项依据:研究意义、国内外研究现状、本项目研究思路"\n'
            '  "yanjiuneirong" -> "(二)研究内容:研究目标、研究内容(3-4项)、关键科学问题(2条)"\n'
            '  "yanjiufangan" -> "(三)研究方案:技术路线、可行性分析、特色与创新(2-3条)、年度计划、预期成果"\n'
            '  "yanjiujichu" -> "(四)研究基础:研究基础与可行性分析、工作条件"\n'
            "每个章节生成2-5个引导性问题。输出ONLY JSON，格式:\n"
            '{"schema_version":"v1","sections":['
            '{"section_key":"lixiangyiju","title":"(一)立项依据","questions":["Q1","Q2"]},'
            '{"section_key":"yanjiuneirong","title":"(二)研究内容","questions":["Q1","Q2"]},'
            '{"section_key":"yanjiufangan","title":"(三)研究方案","questions":["Q1","Q2"]},'
            '{"section_key":"yanjiujichu","title":"(四)研究基础","questions":["Q1","Q2"]}'
            "]}"
        )
        user = f"研究方向: {source}"
        raw = self._call(system, user)
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"schema_version": "v1", "source": source, "sections": []}
        if "schema_version" not in payload:
            payload["schema_version"] = "v1"
        if "sections" not in payload:
            payload["sections"] = []
        try:
            validate_planner_output(payload)
        except SchemaError:
            payload = {"schema_version": "v1", "source": source, "sections": []}
        return payload

    def write(self, *, section_id: str, answers: dict[str, str],
              file_refs: list[dict[str, Any]] | None = None, deterministic: bool = False,
              evidence_context: str | None = None) -> AIResult:
        budget = apply_context_budget(retrieval=[], memory=[], file_refs=file_refs or [], model_max_tokens=None)
        ctx = summarize_file_refs(budget.file_refs)
        user = f"章节: {section_id}\n\n用户回答:\n" + "\n".join(f"Q: {k}\nA: {v}" for k, v in answers.items())
        if ctx:
            user += f"\n\n参考资料:\n{ctx}"
        system = NSFC_WRITER_SYSTEM
        if evidence_context is not None:
            system += (
                '\n\n证据约束：只能依据 evidence_context 陈述事实。'
                '输出单个 JSON 对象，字段为 schema_version、section_key、draft_markdown、evidence_ids、warnings、missing_evidence。'
                'evidence_ids 必须是实际使用的整数 evidence_id；无证据时使用空列表并说明 missing_evidence。'
            )
            user += f"\n\nevidence_context:\n{evidence_context}"
        draft = self._call(system, user, max_tokens=8192)
        return AIResult(text=draft, usage_tokens=len(draft.split()), model_id=self.model)

    def revise(self, *, base_text: str, change_request: str,
               file_refs: list[dict[str, Any]] | None = None, deterministic: bool = False) -> AIResult:
        budget = apply_context_budget(retrieval=[], memory=[], file_refs=file_refs or [], model_max_tokens=None)
        ctx = summarize_file_refs(budget.file_refs)
        user = f"原文:\n{base_text}\n\n修改要求:\n{change_request}"
        if ctx:
            user += f"\n\n参考资料:\n{ctx}"
        revised = self._call(NSFC_REVISER_SYSTEM, user, max_tokens=8192)
        diff = diff_texts(base_text, revised)
        return AIResult(text=revised, usage_tokens=len(revised.split()), model_id=self.model)

    def format_final(self, *, full_text: str, template_hint: str | None = None,
                     file_refs: list[dict[str, Any]] | None = None, deterministic: bool = False) -> AIResult:
        budget = apply_context_budget(retrieval=[], memory=[], file_refs=file_refs or [], model_max_tokens=None)
        ctx = summarize_file_refs(budget.file_refs)
        user = full_text
        if template_hint:
            user = f"模板: {template_hint}\n\n{user}"
        if ctx:
            user += f"\n\n参考资料:\n{ctx}"
        formatted = self._call(NSFC_FORMATTER_SYSTEM, user, max_tokens=16384)
        return AIResult(text=formatted, usage_tokens=len(formatted.split()), model_id=self.model)
