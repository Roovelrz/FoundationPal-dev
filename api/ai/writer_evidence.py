import json
import re
from dataclasses import dataclass

from django.db.models import Q

from ai.models import EvidenceUsage
from ai.domain_retrieval import EvidenceQuery, RuleQuery
from ai.query_router import retrieve_dual
from ai.validators import SchemaError, validate_writer_output


def build_query(section_id, answers):
    return ' '.join([section_id, *[str(value) for key, value in (answers or {}).items() if not str(key).startswith('_')]]).strip()


@dataclass(frozen=True)
class WriterEvidenceContexts:
    query: str
    rule_candidates: list[dict]
    user_evidence_candidates: list[dict]
    result: object

    @property
    def allowed_chunk_ids(self):
        return [item['chunk_id'] for item in self.rule_candidates + self.user_evidence_candidates]


def _rule_candidates(result):
    return [{
        'chunk_id': item['chunk_id'], 'document_name': item['source_document'],
        'page_start': item['page_number'] or 1, 'page_end': item['page_number'] or 1,
        'is_uploaded_material': bool(item.get('is_uploaded_material')),
        'section_title': _section_label(item.get('section_title'), item.get('chunk_index')),
        'text': item['original_text'], 'final_rank': rank,
        'dense_score': item['retrieval_score'], 'domain': 'grant_rule',
    } for rank, item in enumerate((result or {}).get('results', []), start=1)]


def _user_evidence_candidates(result):
    return [{
        'chunk_id': item['chunk_id'], 'document_name': item['document_name'],
        'page_start': item['page_number'] or 1, 'page_end': item['page_number'] or 1,
        'is_uploaded_material': bool(item.get('is_uploaded_material')),
        'section_title': _section_label(item.get('section_title'), item.get('chunk_index')),
        'text': item['text'], 'final_rank': rank,
        'dense_score': item['retrieval_score'], 'domain': 'user_evidence',
    } for rank, item in enumerate((result or {}).get('results', []), start=1)]


def _section_label(section_title, chunk_index=None):
    title = str(section_title or '').strip()
    if title:
        return title
    try:
        return f'文本片段 {int(chunk_index) + 1}'
    except (TypeError, ValueError):
        return '文本片段'


def _fallback_rule_candidates(*, organization_id, proposal_id, query):
    """Use uploaded guideline chunks when a project has no compiled rule pack yet."""
    from ai.models import AIChunk

    if not organization_id:
        return []
    scope = Q(resource__proposal_id=proposal_id) if proposal_id is not None else Q(resource__proposal_id__isnull=True)
    rows = list(
        AIChunk.objects.select_related('resource')
        .filter(
            scope,
            resource__organization_id=str(organization_id),
            resource__source_type='guideline',
            resource__is_deleted=False,
        )
        .order_by('resource_id', 'chunk_index')[:20]
    )
    terms = [term for term in re.split(r'\s+', query) if term]
    ranked = sorted(
        rows,
        key=lambda item: (-sum(item.text.count(term) for term in terms), item.resource_id, item.chunk_index),
    )[:3]
    return [
        {
            'chunk_id': item.id,
            'document_name': item.resource.display_name or item.resource.title or '用户上传指南',
            'page_start': item.page_start or 1,
            'page_end': item.page_end or 1,
            'is_uploaded_material': bool(item.resource.original_filename and item.resource.proposal_id == proposal_id),
            'section_title': _section_label(item.section_title, item.chunk_index),
            'text': item.text,
            'final_rank': index,
            'dense_score': 0.0,
            'domain': 'grant_rule',
        }
        for index, item in enumerate(ranked, start=1)
    ]


def retrieve_writer_evidence(section_id, answers, *, organization_id='', proposal_id=None, owner_id=None):
    query = build_query(section_id, answers)
    raw_version = (answers or {}).get('_pack_version_id')
    try:
        pack_version_id = int(raw_version) if raw_version else None
    except (TypeError, ValueError):
        pack_version_id = None
    result = retrieve_dual(
        question=query,
        rule_query=RuleQuery(
            pack_version_id=pack_version_id,
            program_type=str((answers or {}).get('_program_type', '')),
            year=(int((answers or {}).get('_year')) if str((answers or {}).get('_year', '')).isdigit() else None),
            region=str((answers or {}).get('_region', '')),
            section_key=section_id,
            user_question=query,
        ) if pack_version_id else None,
        evidence_query=EvidenceQuery(
            organization_id=str(organization_id or ''), proposal_id=proposal_id, owner_id=owner_id,
            section_key=section_id, user_question=query,
        ) if organization_id else None,
    )
    rule_candidates = _rule_candidates({'results': result.context_budget['rule_context']})
    if not rule_candidates:
        rule_candidates = _fallback_rule_candidates(
            organization_id=organization_id,
            proposal_id=proposal_id,
            query=query,
        )
    return WriterEvidenceContexts(
        query=query,
        rule_candidates=rule_candidates,
        user_evidence_candidates=_user_evidence_candidates({'results': result.context_budget['evidence_context']}),
        result=result,
    )


def render_evidence_context(candidates):
    if not candidates:
        return ''
    blocks = []
    for candidate in candidates:
        page_line = (
            f'页码：{candidate["page_start"]}-{candidate["page_end"]}\n'
            if candidate.get('is_uploaded_material') else ''
        )
        blocks.append(
            f'[evidence_id={candidate["chunk_id"]}]\n'
            f'文档：{candidate["document_name"]}\n'
            f'{page_line}'
            f'章节：{candidate["section_title"] or "未识别"}\n'
            f'正文：{candidate["text"]}'
        )
    return '\n\n'.join(blocks)


def render_writer_contexts(contexts):
    return (
        render_evidence_context(contexts.rule_candidates),
        render_evidence_context(contexts.user_evidence_candidates),
    )


def parse_writer_result(section_id, raw_text, allowed_chunk_ids):
    text = str(raw_text or '').strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text, flags=re.IGNORECASE).strip()
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        if text.startswith('{') or text.startswith('['):
            raise SchemaError('writer_output_not_valid_json')
        return {
            'schema_version': 'v1',
            'section_key': section_id,
            'draft_markdown': text,
            'evidence_ids': [],
            'warnings': ['provider_did_not_return_evidence_ids'],
            'missing_evidence': [],
        }
    if not isinstance(value, dict):
        raise SchemaError('writer_evidence_not_object')
    if value.get('schema_version') in ('1.0', 1.0, 1):
        value['schema_version'] = 'v1'
    value.setdefault('schema_version', 'v1')
    value['section_key'] = section_id
    for key in ('warnings', 'missing_evidence'):
        if not isinstance(value.get(key), list):
            value[key] = [str(value[key])] if value.get(key) else []
    raw_ids = value.get('evidence_ids')
    if not isinstance(raw_ids, list):
        raw_ids = []
    normalized_ids = []
    ignored_ids = False
    allowed = set(allowed_chunk_ids)
    for item in raw_ids:
        if isinstance(item, bool):
            ignored_ids = True
            continue
        if isinstance(item, str) and item.isdigit():
            item = int(item)
        if not isinstance(item, int) or item not in allowed:
            ignored_ids = True
            continue
        normalized_ids.append(item)
    value['evidence_ids'] = list(dict.fromkeys(normalized_ids))
    if ignored_ids:
        value['warnings'].append('unrecognized_evidence_ids_removed')
    validate_writer_output(value)
    return value


def persist_evidence_usage(*, section, job, run, role, query, candidates, cited_chunk_ids, retrieval_run_id=None, prompt_version=1):
    cited = set(cited_chunk_ids)
    EvidenceUsage.objects.filter(ai_job=job, role=role).delete() if job else None
    for candidate in candidates:
        EvidenceUsage.objects.create(
            workflow_run=run,
            ai_job=job,
            proposal_section=section,
            chunk_id=candidate['chunk_id'],
            role=role,
            evidence_domain=candidate['domain'],
            retrieval_run_id=retrieval_run_id or None,
            query_id=str(retrieval_run_id or ''),
            injection_role=candidate['domain'],
            retrieval_query=query,
            rank=candidate['final_rank'],
            similarity_score=candidate['dense_score'],
            used_in_prompt=True,
            cited_by_model=candidate['chunk_id'] in cited,
            evidence_alias=f'E{candidate["final_rank"]}',
            snapshot_text=candidate['text'],
            document_name_snapshot=candidate['document_name'],
            page_start_snapshot=candidate['page_start'],
            page_end_snapshot=candidate['page_end'],
            section_title_snapshot=candidate['section_title'],
            prompt_version=prompt_version,
        )
