import json
from dataclasses import dataclass

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
        'section_title': '', 'text': item['original_text'], 'final_rank': rank,
        'dense_score': item['retrieval_score'], 'domain': 'grant_rule',
    } for rank, item in enumerate((result or {}).get('results', []), start=1)]


def _user_evidence_candidates(result):
    return [{
        'chunk_id': item['chunk_id'], 'document_name': item['document_name'],
        'page_start': item['page_number'] or 1, 'page_end': item['page_number'] or 1,
        'section_title': '', 'text': item['text'], 'final_rank': rank,
        'dense_score': item['retrieval_score'], 'domain': 'user_evidence',
    } for rank, item in enumerate((result or {}).get('results', []), start=1)]


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
    return WriterEvidenceContexts(
        query=query,
        rule_candidates=_rule_candidates({'results': result.context_budget['rule_context']}),
        user_evidence_candidates=_user_evidence_candidates({'results': result.context_budget['evidence_context']}),
        result=result,
    )


def render_evidence_context(candidates):
    if not candidates:
        return '无可用证据。必须在 missing_evidence 中说明证据不足。'
    blocks = []
    for candidate in candidates:
        blocks.append(
            f'[evidence_id={candidate["chunk_id"]}]\n'
            f'文档：{candidate["document_name"]}\n'
            f'页码：{candidate["page_start"]}-{candidate["page_end"]}\n'
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
    try:
        value = json.loads(raw_text)
    except (TypeError, json.JSONDecodeError):
        return {
            'schema_version': 'v1',
            'section_key': section_id,
            'draft_markdown': raw_text,
            'evidence_ids': [],
            'warnings': ['provider_did_not_return_evidence_ids'],
            'missing_evidence': [],
        }
    if not isinstance(value, dict):
        raise SchemaError('writer_evidence_not_object')
    value.setdefault('schema_version', 'v1')
    value.setdefault('section_key', section_id)
    value.setdefault('warnings', [])
    value.setdefault('missing_evidence', [])
    validate_writer_output(value)
    evidence_ids = value['evidence_ids']
    if not all(isinstance(item, int) for item in evidence_ids):
        raise SchemaError('evidence_ids must contain integers')
    if not set(evidence_ids).issubset(set(allowed_chunk_ids)):
        raise SchemaError('evidence_ids_not_in_retrieval_candidates')
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
