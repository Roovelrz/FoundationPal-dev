import json
from typing import Any
from .base import BaseProvider, AIResult
from ai.validators import (
    validate_planner_output,
    validate_writer_output,
    validate_reviser_output,
    validate_formatter_output,
    SchemaError,
    section_draft,
)
from .util import summarize_file_refs
from ai.context_budget import apply_context_budget
from ai.diff_engine import diff_texts


class Gpt5Provider(BaseProvider):
    def plan(self, *, grant_url: str | None, text_spec: str | None, application_system: str = 'nsfc') -> dict:
        sections = [
            {'section_key': 'summary', 'title': 'Executive Summary', 'questions': ['objective', 'impact', 'outcomes']},
            {'section_key': 'narrative', 'title': 'Project Narrative', 'questions': ['background', 'approach', 'risks']},
            {'section_key': 'budget', 'title': 'Budget', 'questions': ['items', 'totals', 'justification']},
        ]
        payload = {'schema_version': 'v1', 'source': grant_url or 'text', 'sections': sections, 'model': 'gpt-5'}
        try:
            validate_planner_output(payload)
        except SchemaError:
            # In stub context just raise; real provider would attempt repair
            raise
        return payload

    def write(
        self,
        *,
        section_id: str,
        answers: dict[str, str],
        file_refs: list[dict[str, Any]] | None = None,
        deterministic: bool = False,
        evidence_context: str | None = None,
        rule_context: str | None = None,
        user_evidence_context: str | None = None,
        application_system: str = 'nsfc',
    ) -> AIResult:
        # Placeholder: retrieval & memory not yet passed into provider; budget manager still invoked for future parity.
        budget = apply_context_budget(
            retrieval=[],
            memory=[],
            file_refs=file_refs or [],
            model_max_tokens=None,
        )
        draft = f'[gpt-5] Draft for {section_id}:\n' + '\n'.join(f'- {k}: {v}' for k, v in answers.items())
        ctx = summarize_file_refs(budget.file_refs)
        payload = section_draft(section_id, draft + ctx)
        return AIResult(text=payload['draft_markdown'], usage_tokens=0, model_id='gpt-5')

    def revise(
        self,
        *,
        base_text: str,
        change_request: str,
        file_refs: list[dict[str, Any]] | None = None,
        deterministic: bool = False,
        application_system: str = 'nsfc',
    ) -> AIResult:
        """Return a revised text plus structured diff.

        This stub provider deterministically constructs a revision rather than
        calling an external model. We still run through the validation layer
        so contract regressions are caught in tests.
        """
        budget = apply_context_budget(
            retrieval=[],
            memory=[],
            file_refs=file_refs or [],
            model_max_tokens=None,
        )
        # Build revised text (strip to normalize whitespace for diff stability)
        text = base_text.rstrip() + '\n\n[gpt-5] Changes: ' + change_request.strip()
        ctx = summarize_file_refs(budget.file_refs)
        revised = text + ctx
        diff = diff_texts(base_text, revised)
        payload = {'revised': revised, 'diff': diff}
        validate_reviser_output(payload)
        return AIResult(text=revised, usage_tokens=0, model_id='gpt-5')

    def pre_review(self, *, section_title: str, draft: str, application_system: str = 'nsfc') -> AIResult:
        payload = {
            'summary': f'已完成对{section_title}的章节预评审。',
            'strengths': ['草稿已围绕章节主题组织内容。'],
            'issues': [{
                'problem': '需要核对章节内容是否完整回应规划问题。',
                'reason': f'当前草稿长度为{len(draft.strip())}个字符，无法据此确认问题覆盖完整。',
                'direction': '逐项补足问题对应的论证、依据和实施内容。',
            }],
        }
        return AIResult(text=json.dumps(payload, ensure_ascii=False), usage_tokens=0, model_id='gpt-5')

    def format_final(
        self,
        *,
        full_text: str,
        template_hint: str | None = None,
        file_refs: list[dict[str, Any]] | None = None,
        deterministic: bool = False,
        application_system: str = 'nsfc',
    ) -> AIResult:
        budget = apply_context_budget(
            retrieval=[],
            memory=[],
            file_refs=file_refs or [],
            model_max_tokens=None,
        )
        ctx = summarize_file_refs(budget.file_refs)
        payload = {'formatted_markdown': full_text + ctx}
        validate_formatter_output(payload)
        return AIResult(text=payload['formatted_markdown'], usage_tokens=0, model_id='gpt-5')
