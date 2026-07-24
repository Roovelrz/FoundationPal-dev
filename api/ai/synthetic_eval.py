import json
import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any


PROMPT_VERSION = 'synthetic_eval_v1'
QUERY_TYPES = {'direct', 'paraphrase', 'condition', 'negative', 'multi_info'}


@dataclass(frozen=True)
class SyntheticEvalRequest:
    chunk_id: int
    resource_id: int
    source_type: str
    parser_version: str
    query_type: str
    evidence: str


def extract_json_object(raw: str) -> dict[str, Any]:
    cleaned = (raw or '').strip()
    if cleaned.startswith('```'):
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)
    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise ValueError('synthetic_eval_not_object')
    return value


def build_case(request: SyntheticEvalRequest, raw: str, case_id: str, model_name: str) -> dict[str, Any] | None:
    value = extract_json_object(raw)
    if value.get('usable') is not True:
        return None
    query = str(value.get('query', '')).strip()
    reference_answer = str(value.get('reference_answer', '')).strip()
    query_type = str(value.get('query_type', '')).strip()
    if not query or not reference_answer or query_type not in QUERY_TYPES:
        raise ValueError('synthetic_eval_invalid_fields')
    if query_type != request.query_type:
        raise ValueError('synthetic_eval_query_type_mismatch')
    evidence_hash = sha256(request.evidence.encode('utf-8')).hexdigest()
    return {
        'case_id': case_id,
        'query': query,
        'reference_answer': reference_answer,
        'source_chunk_ids': [request.chunk_id],
        'source_document_ids': [request.resource_id],
        'source_type': request.source_type,
        'query_type': query_type,
        'answerable': True,
        'gold_mode': 'synthetic_initial',
        'generated_by': model_name,
        'generation_prompt_version': PROMPT_VERSION,
        'source_parser_version': request.parser_version,
        'source_evidence_sha256': evidence_hash,
    }
