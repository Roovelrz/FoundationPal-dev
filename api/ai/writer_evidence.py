import json

from ai.models import EvidenceUsage
from ai.retrieval import RetrievalService
from ai.validators import SchemaError, validate_writer_output


def build_query(section_id, answers):
    return ' '.join([section_id, *[str(value) for key, value in (answers or {}).items() if not str(key).startswith('_')]]).strip()


def retrieve_writer_evidence(section_id, answers, *, organization_id='', proposal_id=None):
    query = build_query(section_id, answers)
    candidates = RetrievalService().retrieve(
        query,
        organization_id=organization_id,
        proposal_id=proposal_id,
        dense_top_k=20,
        final_top_k=5,
        token_budget=1200,
    )
    return query, candidates


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


def persist_evidence_usage(*, section, job, run, role, query, candidates, cited_chunk_ids, prompt_version=1):
    cited = set(cited_chunk_ids)
    EvidenceUsage.objects.filter(ai_job=job, role=role).delete() if job else None
    for candidate in candidates:
        EvidenceUsage.objects.create(
            workflow_run=run,
            ai_job=job,
            proposal_section=section,
            chunk_id=candidate['chunk_id'],
            role=role,
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
