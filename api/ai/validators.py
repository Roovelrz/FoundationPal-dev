from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


SCHEMA_VERSION = 'v1'
MAX_SECTIONS = 12
MAX_QUESTIONS_PER_SECTION = 20
MAX_SECTION_KEY_LENGTH = 128
MAX_TITLE_LENGTH = 256
MAX_QUESTION_LENGTH = 500
MAX_DRAFT_LENGTH = 20000
REVIEW_DECISIONS = {'approve', 'rewrite', 'human_review'}


class SchemaError(ValueError):
    pass


@dataclass(frozen=True)
class WorkflowError:
    error_code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    source_type: str
    source_ref: str
    excerpt: str = ''


@dataclass(frozen=True)
class ToolInput:
    schema_version: str
    tool_name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    schema_version: str
    tool_name: str
    success: bool
    data: dict[str, Any]
    error: WorkflowError | None = None


def invalid_output_error(error: SchemaError) -> WorkflowError:
    return WorkflowError(
        error_code='invalid_provider_output',
        message=str(error),
        retryable=False,
    )


def _require(obj: dict[str, Any], key: str, typ: type | tuple[type, ...], *, allow_empty: bool = False) -> Any:
    if key not in obj:
        raise SchemaError(f'missing key: {key}')
    value = obj[key]
    if not isinstance(value, typ):
        raise SchemaError(f'{key} wrong type')
    if not allow_empty and value in ('', []):
        raise SchemaError(f'{key} empty not allowed')
    return value


def _validate_version(data: dict[str, Any]) -> None:
    if _require(data, 'schema_version', str) != SCHEMA_VERSION:
        raise SchemaError(f'unsupported schema_version: {data["schema_version"]}')


def validate_planner_output(data: dict[str, Any]) -> dict[str, Any]:
    _validate_version(data)
    sections = _require(data, 'sections', list)
    if len(sections) > MAX_SECTIONS:
        raise SchemaError('sections exceeds maximum')

    seen_keys: set[str] = set()
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            raise SchemaError(f'sections[{index}] not object')
        section_key = _require(section, 'section_key', str)
        title = _require(section, 'title', str)
        questions = _require(section, 'questions', list)
        if len(section_key) > MAX_SECTION_KEY_LENGTH or not section_key.strip():
            raise SchemaError(f'sections[{index}].section_key invalid')
        if section_key in seen_keys:
            raise SchemaError(f'duplicate section_key: {section_key}')
        seen_keys.add(section_key)
        if len(title) > MAX_TITLE_LENGTH or not title.strip():
            raise SchemaError(f'sections[{index}].title invalid')
        if not questions or len(questions) > MAX_QUESTIONS_PER_SECTION:
            raise SchemaError(f'sections[{index}].questions invalid length')
        for question_index, question in enumerate(questions):
            if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION_LENGTH:
                raise SchemaError(f'sections[{index}].questions[{question_index}] invalid')
    return data


def validate_writer_output(data: dict[str, Any]) -> dict[str, Any]:
    _validate_version(data)
    _require(data, 'section_key', str)
    draft = _require(data, 'draft_markdown', str)
    if len(draft) > MAX_DRAFT_LENGTH or draft.lstrip().startswith('{'):
        raise SchemaError('draft_markdown invalid')
    for key in ('evidence_ids', 'warnings', 'missing_evidence'):
        _require(data, key, list, allow_empty=True)
    return data


def section_draft(section_key: str, draft_markdown: str) -> dict[str, Any]:
    data = {
        'schema_version': SCHEMA_VERSION,
        'section_key': section_key,
        'draft_markdown': draft_markdown,
        'evidence_ids': [],
        'warnings': [],
        'missing_evidence': [],
    }
    return validate_writer_output(data)


def validate_reviewer_output(data: dict[str, Any]) -> dict[str, Any]:
    _validate_version(data)
    _require(data, 'section_key', str)
    decision = _require(data, 'decision', str)
    if decision not in REVIEW_DECISIONS:
        raise SchemaError(f'unknown review decision: {decision}')
    for key in ('issues', 'required_changes', 'protected_facts', 'evidence_gaps'):
        _require(data, key, list, allow_empty=True)
    return data


def reviewer_or_human_review(data: dict[str, Any]) -> dict[str, Any]:
    try:
        return validate_reviewer_output(data)
    except SchemaError as error:
        return {
            'schema_version': SCHEMA_VERSION,
            'section_key': str(data.get('section_key') or ''),
            'decision': 'human_review',
            'issues': [str(error)],
            'required_changes': [],
            'protected_facts': [],
            'evidence_gaps': [],
        }


def validate_reviser_output(data: dict[str, Any]) -> dict[str, Any]:
    _require(data, 'revised', str)
    diff = _require(data, 'diff', dict)
    if 'blocks' not in diff:
        if isinstance(diff.get('added'), list) and isinstance(diff.get('removed'), list):
            return data
        raise SchemaError('diff must contain blocks list')
    if not isinstance(diff['blocks'], list):
        raise SchemaError('diff must contain blocks list')
    for block in diff['blocks']:
        if not isinstance(block, dict):
            raise SchemaError('diff block must be object')
        _require(block, 'type', str)
        _require(block, 'before', str, allow_empty=True)
        _require(block, 'after', str, allow_empty=True)
        similarity = _require(block, 'similarity', (int, float))
        if not 0 <= similarity <= 1:
            raise SchemaError('diff block similarity must be between 0 and 1')
    return data


def validate_formatter_output(data: dict[str, Any]) -> dict[str, Any]:
    _require(data, 'formatted_markdown', str)
    return data


ROLE_VALIDATORS = {
    'plan': validate_planner_output,
    'write': validate_writer_output,
    'review': validate_reviewer_output,
    'revise': validate_reviser_output,
    'format': validate_formatter_output,
}


def validate_role_output(role: str, data: dict[str, Any]) -> dict[str, Any]:
    try:
        validator = ROLE_VALIDATORS[role]
    except KeyError as error:
        raise SchemaError(f'unknown role {role}') from error
    return validator(data)
