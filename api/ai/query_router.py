import uuid
import re
from dataclasses import asdict, dataclass, replace

from .domain_retrieval import EvidenceQuery, RuleQuery, RuleRAGService, UserEvidenceRAGService


RULE_TERMS = ('指南', '规则', '要求', '资格', '预算', '经费', '字数', '格式', '符合')
EVIDENCE_TERMS = ('成果', '论文', '专利', '实验', '数据', '团队', '项目', '材料支持')


@dataclass(frozen=True)
class QueryIntent:
    intent: str
    reason: str
    required_domains: tuple[str, ...]
    confidence: float


@dataclass(frozen=True)
class DualRetrievalResult:
    intent: dict
    rule_query: dict | None
    rule_results: dict | None
    evidence_query: dict | None
    user_evidence_results: dict | None
    context_budget: dict
    requirement_gaps: list[str]
    evidence_gaps: list[str]
    conflicts: list[dict]
    retrieval_run_id: str

    def as_dict(self) -> dict:
        return asdict(self)


def route_query(question: str) -> QueryIntent:
    text = question or ''
    has_rule = any(term in text for term in RULE_TERMS)
    has_evidence = any(term in text for term in EVIDENCE_TERMS)
    if has_rule and has_evidence:
        return QueryIntent('dual_grounding', 'contains rule and evidence terms', ('grant_rule', 'user_evidence'), 0.9)
    if has_rule:
        intent = 'rule_validation' if '符合' in text else 'rule_only'
        return QueryIntent(intent, 'contains rule terms', ('grant_rule',), 0.85)
    if has_evidence:
        intent = 'fact_validation' if '支持' in text else 'user_evidence_only'
        return QueryIntent(intent, 'contains evidence terms', ('user_evidence',), 0.85)
    return QueryIntent('dual_grounding', 'ambiguous question uses both domains', ('grant_rule', 'user_evidence'), 0.4)


def split_dual_query(question: str) -> tuple[str, str]:
    '''Split a mixed question into domain-specific retrieval text without dropping ambiguous clauses.'''
    text = (question or '').strip()
    clauses = [item.strip() for item in re.split(r'[。！？；;\n]+', text) if item.strip()]
    rule_clauses = [item for item in clauses if any(term in item for term in RULE_TERMS)]
    evidence_clauses = [item for item in clauses if any(term in item for term in EVIDENCE_TERMS)]
    rule_text = ' '.join(rule_clauses) or text
    evidence_text = ' '.join(evidence_clauses) or text
    return rule_text, evidence_text


def search_grant_rules(query: RuleQuery) -> dict:
    return RuleRAGService().search(query)


def search_user_evidence(query: EvidenceQuery) -> dict:
    return UserEvidenceRAGService().search(query)


def _context_budget(rule_result: dict, evidence_result: dict) -> dict:
    rules = list(rule_result.get('results', []))
    evidence = list(evidence_result.get('results', []))
    rule_context = rules[:2]
    evidence_context = evidence[:2]
    flexible = []
    if len(rules) > 2 and len(evidence) <= 2:
        flexible = [('grant_rule', rules[2])]
    elif len(evidence) > 2 and len(rules) <= 2:
        flexible = [('user_evidence', evidence[2])]
    elif len(rules) > 2:
        flexible = [('grant_rule', rules[2])]
    for domain, item in flexible:
        if domain == 'grant_rule':
            rule_context.append(item)
        else:
            evidence_context.append(item)
    return {
        'rule_context': rule_context,
        'evidence_context': evidence_context,
        'rule_candidate_ids': [item['requirement_id'] for item in rules],
        'evidence_candidate_ids': [item['user_evidence_id'] for item in evidence],
        'rule_context_ids': [item['requirement_id'] for item in rule_context],
        'evidence_context_ids': [item['user_evidence_id'] for item in evidence_context],
        'flexible_context_domain': flexible[0][0] if flexible else None,
        'domain_scores_not_comparable': True,
    }


def retrieve_dual(*, question: str, rule_query: RuleQuery | None, evidence_query: EvidenceQuery | None) -> DualRetrievalResult:
    intent = route_query(question)
    required_domains = ('grant_rule', 'user_evidence') if rule_query and evidence_query else intent.required_domains
    rule_text, evidence_text = split_dual_query(question)
    if rule_query:
        rule_query = replace(rule_query, user_question=rule_text)
    if evidence_query:
        evidence_query = replace(evidence_query, user_question=evidence_text)
    rule_result = search_grant_rules(rule_query) if rule_query and 'grant_rule' in required_domains else None
    evidence_result = search_user_evidence(evidence_query) if evidence_query and 'user_evidence' in required_domains else None
    if 'grant_rule' in required_domains and rule_result is None:
        rule_result = {'status': 'grant_pack_required', 'results': [], 'audit_candidates': []}
    if 'user_evidence' in required_domains and evidence_result is None:
        evidence_result = {'status': 'organization_required', 'results': [], 'audit_candidates': []}
    rule_result = rule_result or {'status': 'not_requested', 'results': [], 'audit_candidates': []}
    evidence_result = evidence_result or {'status': 'not_requested', 'results': [], 'audit_candidates': []}
    requirement_gaps = [] if rule_result['status'] == 'ok' else [rule_result['status']]
    evidence_gaps = [] if evidence_result['status'] == 'ok' else [evidence_result['status']]
    conflicts = [item for item in (rule_result or {}).get('results', []) if item.get('conflict_status') == 'unresolved']
    run_id = str(uuid.uuid4())
    return DualRetrievalResult(
        intent={'intent': intent.intent, 'reason': intent.reason, 'required_domains': list(required_domains), 'confidence': intent.confidence},
        rule_query=rule_query.__dict__ if rule_query else None,
        rule_results=rule_result,
        evidence_query=evidence_query.__dict__ if evidence_query else None,
        user_evidence_results=evidence_result,
        context_budget=_context_budget(rule_result, evidence_result),
        requirement_gaps=requirement_gaps,
        evidence_gaps=evidence_gaps,
        conflicts=conflicts,
        retrieval_run_id=run_id,
    )


def intake_knowledge_snapshot(result: DualRetrievalResult) -> dict:
    rule_results = (result.rule_results or {}).get('results', [])
    evidence_results = (result.user_evidence_results or {}).get('results', [])
    return {
        'resolved_rule_facts': [{'evidence_id': item['requirement_id'], 'source': item['source_document'], 'confidence': item['retrieval_score']} for item in rule_results],
        'resolved_user_facts': [{'evidence_id': item['user_evidence_id'], 'source': item['document_name'], 'confidence': item['retrieval_score']} for item in evidence_results],
        'unresolved_rule_gaps': result.requirement_gaps,
        'unresolved_evidence_gaps': result.evidence_gaps,
        'conflicts': result.conflicts,
        'source_trace': {'retrieval_run_id': result.retrieval_run_id},
    }


def persist_dual_retrieval_trace(workflow_run, result: DualRetrievalResult):
    if workflow_run is None:
        return
    trace = list(workflow_run.trace_json or [])
    trace.append({
        'node': 'dual_retrieval',
        'retrieval_run_id': result.retrieval_run_id,
        'rule_status': (result.rule_results or {}).get('status', 'not_requested'),
        'user_evidence_status': (result.user_evidence_results or {}).get('status', 'not_requested'),
        'rule_candidate_ids': result.context_budget['rule_candidate_ids'],
        'user_evidence_candidate_ids': result.context_budget['evidence_candidate_ids'],
        'rule_context_ids': result.context_budget['rule_context_ids'],
        'user_evidence_context_ids': result.context_budget['evidence_context_ids'],
        'rule_candidate_count': len(result.context_budget['rule_candidate_ids']),
        'user_evidence_candidate_count': len(result.context_budget['evidence_candidate_ids']),
        'normative_query': result.rule_query,
        'factual_query': result.evidence_query,
        'flexible_context_domain': result.context_budget['flexible_context_domain'],
        'domain_scores_not_comparable': True,
    })
    workflow_run.trace_json = trace
    workflow_run.save(update_fields=['trace_json'])
