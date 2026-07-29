import re

from django.db import transaction

from .models import GrantPackDocument, GrantPackVersion, GrantRequirement, RuleConflict, SectionSchema
from .validators import SchemaError


DOCUMENT_TYPE_BY_SOURCE = {
    'guideline': 'guide',
    'call_snapshot': 'notice',
    'template': 'template',
    'review_criteria': 'review',
}
MANDATORY_WORDS = ('必须', '应当', '不得', '限制', '提交', 'must', 'shall', 'require')


def _section_key(value: str, index: int) -> str:
    normalized = re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')
    return normalized[:120] or f'section-{index:03d}'


def _requirement_type(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ('预算', '经费', 'budget')):
        return 'budget'
    if any(word in lowered for word in ('资格', '条件', 'eligib')):
        return 'eligibility'
    if any(word in lowered for word in ('提交', '截止', 'submission')):
        return 'submission'
    if any(word in lowered for word in ('格式', '字数', 'format')):
        return 'format'
    if any(word in lowered for word in ('评审', 'review')):
        return 'review'
    return 'content'


def _extract_atomic_requirements(chunk) -> list[dict]:
    values = []
    for line in re.split(r'\n+|(?<=[。！？.!?])\s*', chunk.text):
        text = line.strip()
        if text and any(word in text.lower() for word in MANDATORY_WORDS):
            values.append({
                'text': text,
                'requirement_type': _requirement_type(text),
                'mandatory': True,
                'applicable_condition': '',
                'target_section': '',
                'validation_method': 'human_review',
                'source_excerpt': text,
                'prompt_version': 1,
            })
    return values


def _validate_requirement(value: dict) -> dict:
    required = {'text', 'requirement_type', 'mandatory', 'applicable_condition', 'target_section', 'validation_method', 'source_excerpt', 'prompt_version'}
    if set(value) != required or not value['text'] or value['requirement_type'] not in {'content', 'format', 'eligibility', 'budget', 'submission', 'review'}:
        raise SchemaError('invalid_rule_requirement_output')
    return value


def bind_rule_pack_documents(*, pack_version: GrantPackVersion, resources) -> list[GrantPackDocument]:
    if pack_version.status != 'draft':
        raise ValueError('rule_pack_version_not_draft')
    resources = list(resources)
    if not resources:
        raise ValueError('rule_pack_requires_documents')
    sha256s = [resource.sha256 for resource in resources]
    if len(sha256s) != len(set(sha256s)):
        raise ValueError('duplicate_rule_pack_document')
    documents = []
    for resource in resources:
        if resource.knowledge_domain != 'grant_rule':
            raise ValueError('rule_pack_requires_grant_rule_resource')
        document_type = DOCUMENT_TYPE_BY_SOURCE.get(resource.source_type)
        if document_type is None:
            raise ValueError('rule_pack_document_type_unknown')
        documents.append(GrantPackDocument.objects.create(
            pack_version=pack_version,
            resource=resource,
            document_type=document_type,
            confidence=1,
        ))
    return documents


@transaction.atomic
def compile_rule_pack(*, pack_version: GrantPackVersion) -> GrantPackVersion:
    if pack_version.status != 'draft':
        raise ValueError('rule_pack_version_not_draft')
    documents = list(pack_version.documents.select_related('resource').prefetch_related('resource__chunks'))
    if not documents:
        raise ValueError('rule_pack_requires_documents')

    GrantRequirement.objects.filter(pack_version=pack_version).delete()
    SectionSchema.objects.filter(pack_version=pack_version).delete()
    RuleConflict.objects.filter(pack_version=pack_version).delete()

    schemas = []
    requirements = []
    for index, document in enumerate(documents, start=1):
        for chunk in document.resource.chunks.order_by('chunk_index'):
            title = chunk.section_title or document.resource.display_name or f'Section {index}'
            schema, _ = SectionSchema.objects.get_or_create(
                pack_version=pack_version,
                section_key=_section_key(title, index),
                defaults={
                    'source_chunk': chunk,
                    'title': title[:256],
                    'order': index,
                    'required': document.document_type == 'template',
                    'field_type': 'markdown',
                },
            )
            schemas.append(schema)
            for value in _extract_atomic_requirements(chunk):
                value = _validate_requirement(value)
                requirement = GrantRequirement.objects.create(
                    pack_version=pack_version,
                    source_chunk=chunk,
                    requirement_type=value['requirement_type'],
                    mandatory=value['mandatory'],
                    target_section=value['target_section'],
                    validation_method=value['validation_method'],
                    text=value['text'],
                    applicable_condition=value['applicable_condition'],
                    source_excerpt=value['source_excerpt'],
                    extraction_prompt_version=value['prompt_version'],
                )
                requirement.target_sections.add(schema)
                requirements.append(requirement)

    seen = {}
    for requirement in requirements:
        key = (requirement.requirement_type, str(requirement.applicability))
        existing = seen.get(key)
        if existing and existing.text != requirement.text:
            RuleConflict.objects.create(
                pack_version=pack_version,
                primary_requirement=existing,
                conflicting_requirement=requirement,
                description='same rule type and applicability have different values',
            )
        else:
            seen[key] = requirement

    pack_version.status = 'needs_review' if RuleConflict.objects.filter(pack_version=pack_version).exists() or any(doc.needs_human_review for doc in documents) else 'validated'
    pack_version.save(update_fields=['status'])
    return pack_version


def publish_rule_pack(*, pack_version: GrantPackVersion) -> GrantPackVersion:
    if pack_version.status != 'validated':
        raise ValueError('rule_pack_not_validated')
    if pack_version.conflicts.filter(human_resolution='').exists():
        raise ValueError('rule_pack_has_unresolved_conflicts')
    pack_version.status = 'published'
    pack_version.save(update_fields=['status'])
    return pack_version
