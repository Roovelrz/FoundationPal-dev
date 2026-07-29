import hashlib
import re

from django.db import transaction

from .embedding_service import EmbeddingService, embed_texts
from .models import AIChunk, AIResource


RULE_CHUNK_TYPES = {'requirement', 'eligibility', 'budget', 'review_criterion', 'section_instruction', 'submission_rule'}
EVIDENCE_CHUNK_TYPES = {'publication', 'project', 'patent', 'experiment', 'dataset', 'equipment', 'team_profile', 'budget_basis'}


def _token_count(text: str) -> int:
    return max(1, len(re.findall(r'\S+', text)))


def _input_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def context_prefix(*, resource: AIResource, knowledge_domain: str, chunk_type: str, section_path: list[str] | None = None) -> str:
    if knowledge_domain == 'grant_rule':
        metadata = resource.metadata or {}
        return '\n'.join([
            '知识域：基金规则',
            f'来源：{resource.display_name}',
            f'规则类型：{chunk_type}',
            f'年度：{metadata.get("year", "")}',
            f'项目类别：{metadata.get("program_type", "")}',
            f'章节：{" / ".join(section_path or [])}',
        ]).strip()
    if knowledge_domain == 'user_evidence':
        return '\n'.join([
            '知识域：用户证据',
            f'来源：{resource.display_name}',
            f'证据类型：{chunk_type}',
            f'组织：{resource.organization_id}',
            f'项目：{resource.proposal_id or ""}',
            f'章节：{" / ".join(section_path or [])}',
        ]).strip()
    raise ValueError('knowledge_domain_required')


def query_embedding_input(*, knowledge_domain: str, text: str) -> str:
    if knowledge_domain == 'grant_rule':
        return f'知识域：基金规则\n查询：{text}'
    if knowledge_domain == 'user_evidence':
        return f'知识域：用户证据\n查询：{text}'
    raise ValueError('knowledge_domain_required')


def split_rule_chunks(text: str) -> list[str]:
    blocks = [item.strip() for item in re.split(r'\n\s*\n|(?=第[一二三四五六七八九十0-9]+[章节条])', text) if item.strip()]
    return blocks or [text.strip()]


def split_user_evidence_chunks(text: str) -> list[str]:
    blocks = [item.strip() for item in re.split(r'\n\s*\n', text) if item.strip()]
    if blocks:
        return blocks
    sentences = [item.strip() for item in re.split(r'(?<=[。！？.!?])\s*', text) if item.strip()]
    out, current = [], []
    for sentence in sentences:
        current.append(sentence)
        if len(' '.join(current)) >= 300:
            out.append(' '.join(current))
            current = []
    if current:
        out.append(' '.join(current))
    return out or [text.strip()]


def chunk_text_for_domain(*, text: str, knowledge_domain: str) -> list[str]:
    if knowledge_domain == 'grant_rule':
        return split_rule_chunks(text)
    if knowledge_domain == 'user_evidence':
        return split_user_evidence_chunks(text)
    raise ValueError('knowledge_domain_required')


@transaction.atomic
def reindex_domain_resource(*, resource: AIResource, index_version: str = 'dual-rag-v1') -> int:
    domain = resource.knowledge_domain
    if domain not in {'grant_rule', 'user_evidence'}:
        raise ValueError('knowledge_domain_required')
    service = EmbeddingService.instance()
    updated = 0
    for chunk in resource.chunks.order_by('chunk_index'):
        chunk_type = chunk.chunk_type
        allowed_types = RULE_CHUNK_TYPES if domain == 'grant_rule' else EVIDENCE_CHUNK_TYPES
        if chunk_type not in allowed_types:
            chunk_type = 'requirement' if domain == 'grant_rule' else 'team_profile'
        section_path = chunk.section_path or chunk.heading_path or []
        prefix = context_prefix(resource=resource, knowledge_domain=domain, chunk_type=chunk_type, section_path=section_path)
        embedding_input = f'{prefix}\n\n{chunk.text}'
        input_hash = _input_hash(embedding_input)
        updates = {
            'knowledge_domain': domain,
            'chunk_type': chunk_type,
            'section_path': section_path,
            'index_namespace': domain,
            'index_version': index_version,
            'embedding_input_hash': input_hash,
            'metadata': {**(chunk.metadata or {}), 'context_prefix': prefix},
        }
        if chunk.embedding_input_hash != input_hash:
            updates.update({
                'embedding': embed_texts([embedding_input])[0],
                'embedding_key': _input_hash(f'{input_hash}:{service.dim}'),
                'embedding_model': service.model_name,
                'embedding_dimension': service.dim,
            })
        AIChunk.objects.filter(pk=chunk.pk).update(**updates)
        updated += 1
    return updated
