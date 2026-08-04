from dataclasses import dataclass
from typing import Any


APPLICATION_SYSTEMS = frozenset({'nsfc', 'provincial', 'university', 'other'})


def normalize_application_system(value: Any) -> str:
    return value if isinstance(value, str) and value in APPLICATION_SYSTEMS else 'nsfc'


@dataclass
class AIResult:
    text: str
    usage_tokens: int = 0
    model_id: str = 'local.stub'


class BaseProvider:
    def plan(
        self,
        *,
        grant_url: str | None,
        text_spec: str | None,
        application_system: str = 'nsfc',
    ) -> dict:  # pragma: no cover - interface
        raise NotImplementedError

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
    ):
        raise NotImplementedError

    def revise(
        self,
        *,
        base_text: str,
        change_request: str,
        file_refs: list[dict[str, Any]] | None = None,
        deterministic: bool = False,
        application_system: str = 'nsfc',
    ):
        raise NotImplementedError

    def pre_review(
        self,
        *,
        section_title: str,
        draft: str,
        application_system: str = 'nsfc',
    ) -> AIResult:
        raise NotImplementedError

    def format_final(
        self,
        *,
        full_text: str,
        template_hint: str | None = None,
        file_refs: list[dict[str, Any]] | None = None,
        deterministic: bool = False,
        application_system: str = 'nsfc',
    ):
        raise NotImplementedError
