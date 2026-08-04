import json
from typing import Dict, Optional, List, Any
from .base import BaseProvider, AIResult


class LocalStubProvider(BaseProvider):
    def plan(self, *, grant_url: str | None, text_spec: str | None, application_system: str = 'nsfc') -> Dict:
        sections = [
            {'section_key': 'summary', 'title': 'Executive Summary', 'questions': ['objective', 'impact']},
            {'section_key': 'narrative', 'title': 'Project Narrative', 'questions': ['background', 'approach']},
            {'section_key': 'budget', 'title': 'Budget', 'questions': ['items', 'total']},
        ]
        return {'schema_version': 'v1', 'source': grant_url or 'text', 'sections': sections}

    def write(
        self,
        *,
        section_id: str,
        answers: Dict[str, str],
        file_refs: Optional[List[Dict[str, Any]]] = None,
        deterministic: bool = False,
        evidence_context: str | None = None,
        rule_context: str | None = None,
        user_evidence_context: str | None = None,
        application_system: str = 'nsfc',
    ) -> AIResult:
        draft = f'Draft for {section_id}:\n' + '\n'.join(f'- {k}: {v}' for k, v in answers.items())
        if deterministic:
            draft = '[deterministic]\n' + draft
        if evidence_context is not None or rule_context is not None or user_evidence_context is not None:
            return AIResult(text=json.dumps({
                'schema_version': 'v1',
                'section_key': section_id,
                'draft_markdown': draft,
                'evidence_ids': [],
                'warnings': [],
                'missing_evidence': ['no_retrieved_evidence'] if not (evidence_context or rule_context or user_evidence_context) else [],
            }), usage_tokens=0)
        return AIResult(text=draft, usage_tokens=0)

    def revise(
        self,
        *,
        base_text: str,
        change_request: str,
        file_refs: Optional[List[Dict[str, Any]]] = None,
        deterministic: bool = False,
        application_system: str = 'nsfc',
    ) -> AIResult:
        new_text = base_text + '\n\nRevisions applied: ' + change_request
        if deterministic:
            new_text = '[deterministic]\n' + new_text
        return AIResult(text=new_text, usage_tokens=0)

    def pre_review(
        self,
        *,
        section_title: str,
        draft: str,
        application_system: str = 'nsfc',
    ) -> AIResult:
        payload = {
            'summary': f'已完成对{section_title}的章节预评审。',
            'strengths': ['草稿已经围绕本章节主题展开，便于后续逐项完善。'],
            'issues': [{
                'problem': '需要进一步核对本章论证是否覆盖所有规划问题。',
                'reason': f'当前草稿长度为{len(draft.strip())}个字符，尚未提供逐项覆盖证明。',
                'direction': '逐项对照本章问题，补足缺失的论证依据和实施细节。',
            }],
        }
        return AIResult(text=json.dumps(payload, ensure_ascii=False), usage_tokens=0)

    def format_final(
        self,
        *,
        full_text: str,
        template_hint: str | None = None,
        file_refs: Optional[List[Dict[str, Any]]] = None,
        deterministic: bool = False,
        application_system: str = 'nsfc',
    ) -> AIResult:
        header = '[stub:formatted]' + (f' template={template_hint}' if template_hint else '')
        if deterministic:
            header += ' deterministic=1'
        return AIResult(text=f'{header}\n\n{full_text}')
