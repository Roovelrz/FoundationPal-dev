import os
import json
from typing import Any
from openai import OpenAI

from .base import BaseProvider, AIResult, normalize_application_system
from ai.validators import (
    validate_planner_output, validate_writer_output,
    validate_reviser_output, validate_formatter_output, SchemaError,
)
from .util import summarize_file_refs
from ai.context_budget import apply_context_budget
from ai.diff_engine import diff_texts
from ai.synthetic_eval import SyntheticEvalRequest

APPLICATION_SYSTEM_PROFILES = {
    'nsfc': {
        'planner_intro': '你是一位国家自然科学基金申请规划专家。突出科学问题、研究逻辑和原创性。',
        'sections': [
            {'section_key': 'lixiangyiju', 'title': '（一）立项依据', 'questions': ['本项目针对的研究对象和应用背景是什么？', '当前研究最需要解决的核心科学问题是什么？']},
            {'section_key': 'yanjiuneirong', 'title': '（二）研究内容', 'questions': ['拟设置的研究目标和三至四项研究内容是什么？', '各项研究内容之间如何形成逻辑递进？']},
            {'section_key': 'yanjiufangan', 'title': '（三）研究方案', 'questions': ['拟采用的技术路线、实验方案和可行性依据是什么？', '项目创新点、年度计划和预期成果分别是什么？']},
            {'section_key': 'yanjiujichu', 'title': '（四）研究基础', 'questions': ['已有工作、数据、平台和团队条件有哪些？', '还需要补充哪些能够证明可行性的材料？']},
        ],
        'writer_system': """你是一位国家自然科学基金申请书撰写专家，有多年成功申请经验。请撰写专业严谨的申请书内容。

写作准则:
1. 客观严谨，用事实和数据说话。多用动宾结构，例如揭示机理、阐明机制、建立模型、突破瓶颈。
2. 避免口语化和夸大表述，禁止使用填补空白、国际领先、世界首次、首创等表述。
3. 立项依据从宏观到微观层层递进：研究领域、研究对象、科学问题、问题剖析、解决思路。
4. 参考文献以近五年为主，权威期刊优先。
5. 研究内容以三至四项为宜，各项相互支撑、环环相扣。
6. 关键科学问题约两条，区分科学问题和技术问题。
7. 全文人称统一使用本项目，不使用我们。
8. 严格遵守调用方指定的输出格式。""",
        'reviser_system': """你是一位国家自然科学基金申请评审专家。根据修改要求和评审标准修订申请书。

评审标准:
1. 科学问题是否聚焦且重要，是否区别于技术或工程问题。
2. 创新性是否实质，而非简单工具套用。
3. 立项依据到研究方案的逻辑链是否完整。
4. 研究方案是否具体可操作。
5. 是否存在夸大表述或遗漏关键前人工作。

常见扣分点包括科学问题太大太空、创新点过多、研究方案不具体、逻辑链断裂。针对标准逐条审查，直接输出修订后文本。""",
        'formatter_system': """你是一位国家自然科学基金申请书排版专家。按国自然申请书习惯排版为完整文档。

格式要求:
- 正文不超过三十页，建议二十页以内
- 参考文献约三十条，编号使用[1][2]...
- 章节标题用##标记，子标题用###标记""",
    },
    'provincial': {
        'planner_intro': '你是一位省级基金申请规划专家。突出地方需求、应用价值、实施路径和可交付成果。',
        'sections': [
            {'section_key': 'background_need', 'title': '（一）背景与需求', 'questions': ['本项目对应的地方发展、产业或公共服务需求是什么？', '拟解决的核心问题及其紧迫性是什么？']},
            {'section_key': 'objectives_tasks', 'title': '（二）目标与任务', 'questions': ['项目总体目标、阶段目标和重点任务分别是什么？', '研究或技术任务如何服务本省支持方向？']},
            {'section_key': 'implementation_outcomes', 'title': '（三）实施方案与成果', 'questions': ['技术路线、实施步骤、时间安排和风险控制如何设计？', '可量化成果、应用对象和预期效益是什么？']},
            {'section_key': 'foundation_conditions', 'title': '（四）基础与条件', 'questions': ['已有基础、团队分工和平台条件有哪些？', '哪些条件能够保障项目按期落地？']},
        ],
        'writer_system': """你是一位省级基金项目申报书撰写专家。突出地方经济社会发展、产业技术或公共服务需求，并说明项目的应用价值和落地路径。

写作时让目标对应支持方向，任务衔接实施计划，成果明确服务对象和可量化指标；如实说明团队、平台和已有基础。避免把省级项目写成空泛的宏大科学命题，也不要夸大效益。全文统一使用本项目，并遵守调用方指定格式。""",
        'reviser_system': """你是一位省级基金项目评审专家。根据修改要求修订申请书。

重点检查项目是否回应明确的地方需求，目标任务是否可执行，技术或研究路线是否与成果指标相衔接，应用对象和预期效益是否具体，团队与条件能否保障实施。删除脱离省级项目定位的空泛表述，直接输出修订后文本。""",
        'formatter_system': """你是一位省级基金项目申报书排版专家。按清晰、便于评审的结构整理完整文档。

使用##和###建立标题层级，突出背景需求、目标任务、实施计划、成果指标和基础条件。若调用方提供模板提示则优先遵守；未提供时不要虚构省份专属页数或格式要求。""",
    },
    'university': {
        'planner_intro': '你是一位校级项目申报规划专家。突出校内需求、现有资源、短周期执行和可量化成果。',
        'sections': [
            {'section_key': 'project_background', 'title': '（一）项目背景', 'questions': ['项目服务的校内教学、科研、管理或平台建设需求是什么？', '现有问题和立项必要性是什么？']},
            {'section_key': 'objectives_tasks', 'title': '（二）目标与任务', 'questions': ['项目目标、重点任务和阶段性里程碑是什么？', '如何利用现有校内资源形成闭环？']},
            {'section_key': 'implementation_plan', 'title': '（三）实施计划', 'questions': ['实施步骤、人员分工、时间安排和风险控制如何设计？', '有哪些可在项目周期内完成的量化结果？']},
            {'section_key': 'conditions_outcomes', 'title': '（四）条件与成果', 'questions': ['已有团队、平台、经费或协作条件有哪些？', '成果将如何服务校内并完成验收或推广？']},
        ],
        'writer_system': """你是一位校级项目申报书撰写专家。围绕校内实际需求写作，突出可利用的团队和平台资源、清晰的短周期实施步骤及可量化成果。

项目目标应服务教学、科研、管理或平台建设等具体场景；任务分工、时间节点和验收成果必须可执行。不要套用国家级项目的宏大表述，也不要虚构校内政策或资源。全文统一使用本项目，并遵守调用方指定格式。""",
        'reviser_system': """你是一位校级项目评审专家。根据修改要求修订申请书。

重点检查立项是否回应校内需求，是否充分利用现有资源，任务与周期是否匹配，成果是否能够量化验收并形成校内应用或推广。删去与校级定位不相称的泛化表述，直接输出修订后文本。""",
        'formatter_system': """你是一位校级项目申报书排版专家。按简洁、清晰、可验收的结构整理完整文档。

使用##和###建立标题层级，突出项目背景、任务安排、实施节点、已有条件和可量化成果。若调用方提供模板提示则优先遵守；未提供时不要假定校内固定页数或表格。""",
    },
    'other': {
        'planner_intro': '你是一位通用研究型项目申报规划专家。以用户材料和委托方要求为准，采用简化但完整的研究逻辑：问题或背景、目标、研究内容、方法、条件与成果。',
        'sections': [
            {'section_key': 'project_background', 'title': '（一）项目背景与问题', 'questions': ['项目面向的研究或应用情境、核心问题和立项必要性是什么？', '研究对象、目标对象或应用边界是什么，已有基础有哪些？']},
            {'section_key': 'objectives', 'title': '（二）目标与研究内容', 'questions': ['总体目标、二至三项具体目标和二至三项研究内容或任务分别是什么？', '各项内容之间如何由问题逐步推进到目标？']},
            {'section_key': 'approach', 'title': '（三）研究方法与实施方案', 'questions': ['针对各项内容拟采用的方法、技术路线、数据或证据来源及可行性依据是什么？', '关键节点、风险与应对措施如何安排？']},
            {'section_key': 'implementation_outcomes', 'title': '（四）条件与预期成果', 'questions': ['人员、平台、数据或资源条件如何支撑项目实施？', '预期成果、可检验指标、交付方式和应用去向是什么？']},
        ],
        'writer_system': """你是一位通用研究型项目申报书撰写专家。优先依据用户材料和委托方要求，采用简化但完整的研究逻辑：问题或背景、目标、研究内容、方法、条件与成果。

研究体系保持精炼：设置二至三项研究内容或任务即可；每项明确对应的问题或目标、采用的方法和预期产出，并说明相互衔接关系。清晰区分用户已提供的事实与尚待补充的信息，不虚构政策、指标、条件或委托方格式。不要擅自套用国自然、省级或校级项目的专属规则，全文统一使用本项目，并遵守调用方指定格式。""",
        'reviser_system': """你是一位通用研究型项目申报评审专家。根据修改要求修订申请书。

重点检查问题或背景、目标、研究内容、方法、条件与成果是否形成完整且简明的逻辑；每项内容是否有明确目的、方法和产出；成果是否可检验；资源、节点与风险安排是否可信。以用户材料和委托方要求为准，不额外假定某类基金规则，直接输出修订后文本。""",
        'formatter_system': """你是一位通用研究型项目申报书排版专家。按完整、易读、便于评审的结构整理文档。

使用##和###建立标题层级，保持问题或背景、目标与研究内容、研究方法、条件与成果的结构清楚。若调用方提供模板提示则优先遵守；未提供时不要虚构特定申报体系的格式限制。""",
    },
}


def _application_profile(application_system: str) -> dict[str, Any]:
    return APPLICATION_SYSTEM_PROFILES[normalize_application_system(application_system)]


def _planner_system(profile: dict[str, Any]) -> str:
    sections = profile['sections']
    fixed_ids = '\n'.join(f'  {item["section_key"]} -> {item["title"]}' for item in sections)
    output_sections = ','.join(
        f'{{"section_key":"{item["section_key"]}","title":"{item["title"]}","questions":["Q1","Q2"]}}'
        for item in sections
    )
    return (
        f'{profile["planner_intro"]}\n'
        '根据研究方向，为以下固定章节生成引导性问题。\n'
        f'必须使用以下固定章节 id:\n{fixed_ids}\n'
        '每个章节生成2至5个引导性问题。输出ONLY JSON，格式:\n'
        '{"schema_version":"v1","sections":[' + output_sections + ']}'
    )


def _fallback_plan(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        'schema_version': 'v1',
        'sections': [
            {
                'section_key': item['section_key'],
                'title': item['title'],
                'questions': list(item['questions']),
            }
            for item in profile['sections']
        ],
    }


class DeepSeekProvider(BaseProvider):
    def __init__(self):
        api_key = os.getenv("DEEPSEEK_API_KEY", "") or os.getenv("LLM_API_KEY", "")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY not set")
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", "") or os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
        self.model = os.getenv("DEEPSEEK_MODEL", "") or os.getenv("LLM_MODEL", "deepseek-chat")
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

    def plan(
        self,
        *,
        grant_url: str | None,
        text_spec: str | None,
        application_system: str = 'nsfc',
    ) -> dict:
        source = grant_url or text_spec or 'N/A'
        profile = _application_profile(application_system)
        system = _planner_system(profile)
        user = f"研究方向: {source}"
        raw = self._call(system, user)
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        if payload.get("schema_version") in ("1.0", 1.0, 1):
            payload["schema_version"] = "v1"
        if "schema_version" not in payload:
            payload["schema_version"] = "v1"
        if "sections" not in payload:
            payload["sections"] = []
        try:
            validate_planner_output(payload)
        except SchemaError:
            payload = _fallback_plan(profile)
        return payload

    def write(self, *, section_id: str, answers: dict[str, str],
              file_refs: list[dict[str, Any]] | None = None, deterministic: bool = False,
              evidence_context: str | None = None, rule_context: str | None = None,
              user_evidence_context: str | None = None, application_system: str = 'nsfc') -> AIResult:
        budget = apply_context_budget(retrieval=[], memory=[], file_refs=file_refs or [], model_max_tokens=None)
        ctx = summarize_file_refs(budget.file_refs)
        user = f"章节: {section_id}\n\n用户回答:\n" + "\n".join(f"Q: {k}\nA: {v}" for k, v in answers.items())
        if ctx:
            user += f"\n\n参考资料:\n{ctx}"
        system = _application_profile(application_system)['writer_system']
        if evidence_context is not None or rule_context is not None or user_evidence_context is not None:
            system += (
                '\n\n证据约束：只能依据 evidence_context 陈述事实。'
                '输出单个 JSON 对象，字段为 schema_version、section_key、draft_markdown、evidence_ids、warnings、missing_evidence。'
                'evidence_ids 必须是实际使用的整数 evidence_id；无证据时使用空列表并说明 missing_evidence。'
            )
            if rule_context is not None:
                user += f"\n\ngrant_rule_context:\n{rule_context}"
            if user_evidence_context is not None:
                user += f"\n\nuser_evidence_context:\n{user_evidence_context}"
            if evidence_context is not None:
                user += f"\n\nevidence_context:\n{evidence_context}"
        draft = self._call(system, user, max_tokens=8192)
        return AIResult(text=draft, usage_tokens=len(draft.split()), model_id=self.model)

    def revise(self, *, base_text: str, change_request: str,
               file_refs: list[dict[str, Any]] | None = None, deterministic: bool = False,
               application_system: str = 'nsfc') -> AIResult:
        budget = apply_context_budget(retrieval=[], memory=[], file_refs=file_refs or [], model_max_tokens=None)
        ctx = summarize_file_refs(budget.file_refs)
        user = f"原文:\n{base_text}\n\n修改要求:\n{change_request}"
        if ctx:
            user += f"\n\n参考资料:\n{ctx}"
        revised = self._call(_application_profile(application_system)['reviser_system'], user, max_tokens=8192)
        diff = diff_texts(base_text, revised)
        return AIResult(text=revised, usage_tokens=len(revised.split()), model_id=self.model)

    def pre_review(self, *, section_title: str, draft: str, application_system: str = 'nsfc') -> AIResult:
        profile = _application_profile(application_system)
        system = (
            f'{profile["planner_intro"]}\n'
            '你是一位严谨、建设性的项目申报章节预评审专家。只评价给定章节，不编造材料或事实。'
            '必须表扬确实存在的优点，也必须指出具体缺点、判断理由和可执行的修改方向。'
            '每个理由要引用或概括草稿中的具体表述、结构或缺失，不能给空泛评价。'
            '输出单个 JSON 对象，字段为 summary、strengths、issues、revision_request。'
            'strengths 是 1 至 3 条字符串；issues 是数组，每项含 problem、reason、direction；'
            'revision_request 汇总可直接用于修订的要求。'
        )
        user = f'章节标题：{section_title}\n\n章节草稿：\n{draft}'
        review = self._call(system, user, max_tokens=4096)
        return AIResult(text=review, usage_tokens=len(review.split()), model_id=self.model)

    def format_final(self, *, full_text: str, template_hint: str | None = None,
                     file_refs: list[dict[str, Any]] | None = None, deterministic: bool = False,
                     application_system: str = 'nsfc') -> AIResult:
        budget = apply_context_budget(retrieval=[], memory=[], file_refs=file_refs or [], model_max_tokens=None)
        ctx = summarize_file_refs(budget.file_refs)
        user = full_text
        if template_hint:
            user = f"模板: {template_hint}\n\n{user}"
        if ctx:
            user += f"\n\n参考资料:\n{ctx}"
        formatted = self._call(_application_profile(application_system)['formatter_system'], user, max_tokens=16384)
        return AIResult(text=formatted, usage_tokens=len(formatted.split()), model_id=self.model)
