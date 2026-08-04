from typing import Dict, Optional, List, Any
from .base import BaseProvider, AIResult
from .gpt5 import Gpt5Provider
from .gemini import GeminiProvider


class CompositeProvider(BaseProvider):
    """Route capabilities: GPT-5 for plan/write; Gemini for revise/formatting."""

    def __init__(self, gpt: BaseProvider | None = None, gemini: BaseProvider | None = None):
        self.gpt = gpt or Gpt5Provider()
        self.gemini = gemini or GeminiProvider()

    def plan(self, *, grant_url: str | None, text_spec: str | None, application_system: str = 'nsfc') -> Dict:
        return self.gpt.plan(
            grant_url=grant_url,
            text_spec=text_spec,
            application_system=application_system,
        )

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
        return self.gpt.write(
            section_id=section_id,
            answers=answers,
            file_refs=file_refs,
            deterministic=deterministic,
            evidence_context=evidence_context,
            rule_context=rule_context,
            user_evidence_context=user_evidence_context,
            application_system=application_system,
        )

    def revise(
        self,
        *,
        base_text: str,
        change_request: str,
        file_refs: Optional[List[Dict[str, Any]]] = None,
        deterministic: bool = False,
        application_system: str = 'nsfc',
    ) -> AIResult:
        return self.gemini.revise(
            base_text=base_text,
            change_request=change_request,
            file_refs=file_refs,
            deterministic=deterministic,
            application_system=application_system,
        )

    def pre_review(self, *, section_title: str, draft: str, application_system: str = 'nsfc') -> AIResult:
        return self.gpt.pre_review(
            section_title=section_title,
            draft=draft,
            application_system=application_system,
        )

    def format_final(
        self,
        *,
        full_text: str,
        template_hint: str | None = None,
        file_refs: Optional[List[Dict[str, Any]]] = None,
        deterministic: bool = False,
        application_system: str = 'nsfc',
    ) -> AIResult:
        return self.gemini.format_final(
            full_text=full_text,
            template_hint=template_hint,
            file_refs=file_refs,
            deterministic=deterministic,
            application_system=application_system,
        )
