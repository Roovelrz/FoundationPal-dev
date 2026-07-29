import hashlib
import json
from collections import Counter
from pathlib import Path

from .domain_retrieval import EvidenceQuery, RuleQuery
from .embedding_service import EmbeddingService
from .models import GrantPackVersion, Phase11SeedMap, UserEvidence
from .query_router import retrieve_dual, search_grant_rules, search_user_evidence


CONTRACT_VERSION = 'phase11-formal-eval-v2'


def _ratio(hit, total):
    return round(hit / total, 4) if total else None


def _maps(prefix=''):
    rows = Phase11SeedMap.objects.filter(kind__startswith=prefix) if prefix else Phase11SeedMap.objects.exclude(kind__startswith='phase11_bge_')
    return {(row.kind.removeprefix(prefix), row.external_id): row.target_id for row in rows}


def _load(root, name):
    return json.loads((Path(root) / name).read_text(encoding='utf-8'))['cases']


def _citation_metrics(root):
    path = Path(root) / '06_claim_citation_entailment_labels.json'
    if not path.exists():
        return {
            'citation_entailment_rate': None,
            'citation_entailment_status': 'unmeasured_requires_claim_to_evidence_labels',
        }
    payload = json.loads(path.read_text(encoding='utf-8'))
    labels = payload['cases']
    counts = Counter(item['label'] for item in labels)
    evaluable = counts['complete_support'] + counts['partial_support'] + counts['unsupported']
    return {
        'citation_label_case_count': len(labels),
        'citation_label_counts': dict(sorted(counts.items())),
        'citation_evaluable_case_count': evaluable,
        'citation_not_evaluable_case_count': counts['not_evaluable'],
        'citation_entailment_rate': _ratio(counts['complete_support'] + counts['partial_support'], evaluable),
        'citation_entailment_status': 'measured_synthetic_test_fixture' if payload.get('annotation_level') == 'synthetic_test_developer_review' else 'measured_developer_initial_review',
        'citation_annotation_level': payload.get('annotation_level', ''),
        'citation_label_fixture': path.name,
    }


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _source_complete(row, domain):
    if domain == 'rule':
        return bool(row.get('chunk_id') and row.get('source_document') and row.get('original_text'))
    return bool(row.get('chunk_id') and row.get('document_name') and row.get('text'))


def _failure_reason(gold, result):
    status = result.get('status')
    if status == 'grant_pack_not_published':
        return 'metadata_filtered'
    if status in {'grant_pack_required', 'organization_required'}:
        return 'metadata_filtered'
    final_ids = {item.get('requirement_id') or item.get('user_evidence_id') for item in result.get('results', [])}
    if gold.intersection(final_ids):
        return None
    if gold.intersection(set(result.get('audit_candidates', []))):
        return 'rerank_miss'
    return 'candidate_miss'


def _case_diagnostic(case, gold, result, *, domain, final_limit):
    final_ids = [item.get('requirement_id') or item.get('user_evidence_id') for item in result.get('results', [])]
    candidate_ids = result.get('audit_candidates', [])
    rank = next((index for index, value in enumerate(candidate_ids, start=1) if value in gold), None)
    return {
        'case_id': case['case_id'],
        'route': domain,
        'sub_queries': [result.get('retrieval_query', case.get('query', ''))],
        'gold_ids': sorted(gold),
        'candidate_ids': candidate_ids,
        'candidate_scores': result.get('audit_candidate_details', []),
        'final_ids': final_ids[:final_limit],
        'gold_rank': rank,
        'applied_metadata_filters': result.get('applied_filters', {}),
        'filter_counts': result.get('filter_counts', {}),
        'status': result.get('status'),
        'failure_reason': _failure_reason(gold, result),
    }


def _mapped_ids(mapping, kind, values):
    missing = [value for value in values if (kind, value) not in mapping]
    return {mapping[(kind, value)] for value in values if (kind, value) in mapping}, missing


def _mixed_proposal_id(mapping, external_evidence_ids):
    evidence_ids, missing = _mapped_ids(mapping, 'user_evidence', external_evidence_ids)
    if missing or not evidence_ids:
        return None, missing
    proposal_ids = set(UserEvidence.objects.filter(pk__in=evidence_ids).values_list('proposal_id', flat=True))
    if len(proposal_ids) != 1 or None in proposal_ids:
        return None, []
    return proposal_ids.pop(), []


def _rule_query(pack_id, case, *, year=None, user_question=None):
    version = GrantPackVersion.objects.select_related('pack__program').get(pk=pack_id)
    program_type = case.get('program_type') or version.pack.program.program_type
    if version.pack.program.program_type == 'phase11_eval':
        program_type = ''
    return RuleQuery(
        pack_version_id=pack_id,
        year=year,
        program_type=program_type,
        region=case.get('region') or version.pack.program.region,
        user_question=user_question if user_question is not None else case['query'],
    )


def run_formal_eval(root, workflow_runtime_report=None, mapping_kind_prefix=''):
    root = Path(root)
    mapping = _maps(mapping_kind_prefix)
    rule_cases = _load(root, '01_rule_requirement_mapping.json')
    evidence_cases = _load(root, '02_user_evidence_grounding.json')
    negatives = _load(root, '03_negative_rule_scope.json')
    mixed = _load(root, '04_mixed_dual_domain.json')
    leakage = _load(root, '05_cross_organization_leakage.json')
    rule_hits = {1: 0, 3: 0, 5: 0}
    rule_candidate_hits = {20: 0, 40: 0}
    rule_rows = []
    source_complete = source_total = 0

    for case in rule_cases:
        gold, missing = _mapped_ids(mapping, 'grant_requirement', case['requirement_ids'])
        if missing or ('grant_pack_version', case['grant_pack_version_id']) not in mapping:
            rule_rows.append({'case_id': case['case_id'], 'failure_reason': 'gold_mapping_error', 'missing_external_ids': missing})
            continue
        pack_id = mapping[('grant_pack_version', case['grant_pack_version_id'])]
        result = search_grant_rules(_rule_query(pack_id, case, year=case['applicable_year']))
        ids = [item['requirement_id'] for item in result.get('results', [])]
        candidates = result.get('audit_candidates', [])
        for k in rule_hits:
            rule_hits[k] += bool(gold.intersection(ids[:k]))
        for k in rule_candidate_hits:
            rule_candidate_hits[k] += bool(gold.intersection(candidates[:k]))
        source_total += len(result.get('results', []))
        source_complete += sum(_source_complete(item, 'rule') for item in result.get('results', []))
        rule_rows.append(_case_diagnostic(case, gold, result, domain='rule', final_limit=5))

    negative_rows = []
    negative_statuses = Counter()
    unpublished_expected_total = unpublished_expected_hits = 0
    no_applicable_expected_total = no_applicable_expected_hits = 0
    for case in negatives:
        pack_id = mapping.get(('grant_pack_version', case['grant_pack_version_id']))
        if not pack_id:
            negative_rows.append({'case_id': case['case_id'], 'status': 'gold_mapping_error'})
            continue
        query = RuleQuery(pack_version_id=pack_id, user_question=case['query'])
        if case['reason'] == 'wrong_year':
            query = RuleQuery(pack_version_id=pack_id, year=case['requested_year'], user_question=case['query'])
        elif case['reason'] == 'wrong_program':
            query = RuleQuery(pack_version_id=pack_id, program_type=case['requested_program_type'], user_question=case['query'])
        elif case['reason'] == 'wrong_region':
            query = RuleQuery(pack_version_id=pack_id, region=case['requested_region'], user_question=case['query'])
        override = case.get('pack_status_override')
        version = GrantPackVersion.objects.get(pk=pack_id) if override else None
        original_status = version.status if version else None
        if version and original_status != override:
            version.status = override
            version.save(update_fields=['status'])
        try:
            result = search_grant_rules(query)
        finally:
            if version and original_status != override:
                version.status = original_status
                version.save(update_fields=['status'])
        status = result['status']
        negative_statuses[status] += 1
        if case.get('expected_status') == 'grant_pack_not_published':
            unpublished_expected_total += 1
            unpublished_expected_hits += status == 'grant_pack_not_published'
        if case.get('expected_status') == 'no_applicable_rule':
            no_applicable_expected_total += 1
            no_applicable_expected_hits += status == 'no_applicable_rule'
        negative_rows.append({'case_id': case['case_id'], 'reason': case['reason'], 'status': status, 'correct_scope_rejection': status == 'no_applicable_rule', 'correct_safety_block': status == 'grant_pack_not_published'})

    evidence_candidate_hits = {20: 0}
    evidence_context_hits = {1: 0, 3: 0, 5: 0, 8: 0}
    evidence_rows = []
    for case in evidence_cases:
        gold, missing = _mapped_ids(mapping, 'user_evidence', case['user_evidence_ids'])
        org_id = mapping.get(('organization', case['organization_id']))
        proposal_id = mapping.get(('proposal', case['proposal_id']))
        if missing or not gold or not org_id or not proposal_id:
            evidence_rows.append({'case_id': case['case_id'], 'failure_reason': 'gold_mapping_error', 'missing_external_ids': missing})
            continue
        result = search_user_evidence(EvidenceQuery(organization_id=str(org_id), proposal_id=proposal_id, user_question=case['query']))
        ids = [item['user_evidence_id'] for item in result.get('results', [])]
        candidates = result.get('audit_candidates', [])
        evidence_candidate_hits[20] += bool(gold.intersection(candidates[:20]))
        for k in evidence_context_hits:
            evidence_context_hits[k] += bool(gold.intersection(ids[:k]))
        source_total += len(result.get('results', []))
        source_complete += sum(_source_complete(item, 'evidence') for item in result.get('results', []))
        evidence_rows.append(_case_diagnostic(case, gold, result, domain='user_evidence', final_limit=8))

    leakage_failures = leakage_authorized_hits = leakage_runnable = 0
    leakage_rows = []
    for case in leakage:
        org_id = mapping.get(('organization', case['authorized_organization_id']))
        authorized, authorized_missing = _mapped_ids(mapping, 'user_evidence', case['authorized_user_evidence_ids'])
        forbidden, missing = _mapped_ids(mapping, 'user_evidence', case['forbidden_user_evidence_ids'])
        proposal_id, proposal_missing = _mixed_proposal_id(mapping, case['authorized_user_evidence_ids'])
        missing_ids = authorized_missing + missing + proposal_missing
        if not org_id or not authorized or not forbidden or not proposal_id or missing_ids:
            leakage_rows.append({'case_id': case['case_id'], 'status': 'gold_mapping_error', 'missing_external_ids': missing_ids})
            continue
        leakage_runnable += 1
        result = search_user_evidence(EvidenceQuery(
            organization_id=str(org_id), proposal_id=proposal_id, user_question=case['query'],
        ))
        returned = {item['user_evidence_id'] for item in result.get('results', [])}
        authorized_returned = sorted(authorized.intersection(returned))
        leaked = sorted(forbidden.intersection(returned))
        leakage_authorized_hits += bool(authorized_returned)
        leakage_failures += bool(leaked)
        leakage_rows.append({
            'case_id': case['case_id'], 'status': result['status'], 'proposal_id': proposal_id,
            'authorized_returned_ids': authorized_returned, 'forbidden_returned_ids': leaked,
        })

    mixed_rule_hits = mixed_evidence_hits = mixed_joint_hits = mixed_runnable = 0
    mixed_rows = []
    for case in mixed:
        rule_gold, rule_missing = _mapped_ids(mapping, 'grant_requirement', case['requirement_ids'])
        evidence_gold, evidence_missing = _mapped_ids(mapping, 'user_evidence', case['user_evidence_ids'])
        pack_id = mapping.get(('grant_pack_version', case['grant_pack_version_id']))
        org_id = mapping.get(('organization', case['organization_id']))
        proposal_id, proposal_missing = _mixed_proposal_id(mapping, case['user_evidence_ids'])
        if rule_missing or evidence_missing or proposal_missing or not rule_gold or not evidence_gold or not pack_id or not org_id or not proposal_id:
            mixed_rows.append({'case_id': case['case_id'], 'failure_reason': 'gold_mapping_error', 'missing_external_ids': rule_missing + evidence_missing + proposal_missing})
            continue
        mixed_runnable += 1
        rule_question = case.get('rule_query') or case['query']
        evidence_question = case.get('evidence_query') or case['query']
        dual_result = retrieve_dual(
            question=f'{rule_question}。{evidence_question}',
            rule_query=_rule_query(pack_id, case, user_question=rule_question),
            evidence_query=EvidenceQuery(organization_id=str(org_id), proposal_id=proposal_id, user_question=evidence_question),
        )
        rule_result = dual_result.rule_results
        evidence_result = dual_result.user_evidence_results
        rule_hit = bool(rule_gold.intersection({item['requirement_id'] for item in rule_result.get('results', [])}))
        evidence_hit = bool(evidence_gold.intersection({item['user_evidence_id'] for item in evidence_result.get('results', [])}))
        mixed_rule_hits += rule_hit
        mixed_evidence_hits += evidence_hit
        mixed_joint_hits += rule_hit and evidence_hit
        mixed_rows.append({
            'case_id': case['case_id'],
            'proposal_id': proposal_id,
            'rule_hit_at_5': rule_hit,
            'evidence_hit_at_8': evidence_hit,
            'joint_hit': rule_hit and evidence_hit,
            'rule_diagnostic': _case_diagnostic(case, rule_gold, rule_result, domain='rule', final_limit=5),
            'evidence_diagnostic': _case_diagnostic(case, evidence_gold, evidence_result, domain='user_evidence', final_limit=8),
            'context_budget': dual_result.context_budget,
        })

    workflow_runtime = None
    if workflow_runtime_report and Path(workflow_runtime_report).exists():
        workflow_runtime = json.loads(Path(workflow_runtime_report).read_text(encoding='utf-8'))
    health = EmbeddingService.instance().health()
    citation = _citation_metrics(root)
    fixture_names = ['01_rule_requirement_mapping.json', '02_user_evidence_grounding.json', '03_negative_rule_scope.json', '04_mixed_dual_domain.json', '05_cross_organization_leakage.json', '06_claim_grounding.json', '07_intake_and_review_workflow.json']
    if (root / '06_claim_citation_entailment_labels.json').exists():
        fixture_names.append('06_claim_citation_entailment_labels.json')
    fixture_files = [root / name for name in fixture_names]
    return {
        'evaluation_scope': 'phase11_verified_fixture_formal_eval',
        'evaluation_contract_version': CONTRACT_VERSION,
        'mapping_kind_prefix': mapping_kind_prefix,
        'runtime_environment': {'embedding': health, 'fixture_sha256': {path.name: _sha256(path) for path in fixture_files}},
        'rule_rag': {
            'case_count': len(rule_cases),
            **{f'candidate_recall_at_{k}': _ratio(value, len(rule_cases)) for k, value in rule_candidate_hits.items()},
            **{f'final_recall_at_{k}': _ratio(value, len(rule_cases)) for k, value in rule_hits.items()},
            'negative_status_counts': dict(sorted(negative_statuses.items())),
            'no_applicable_rule_accuracy': _ratio(no_applicable_expected_hits, no_applicable_expected_total),
            'unpublished_pack_safety_block_rate': _ratio(unpublished_expected_hits, unpublished_expected_total),
            'unpublished_pack_safety_block_status': 'measured' if unpublished_expected_total else 'unmeasured_no_expected_unpublished_cases',
        },
        'user_evidence_rag': {
            'case_count': len(evidence_cases),
            **{f'candidate_recall_at_{k}': _ratio(value, len(evidence_cases)) for k, value in evidence_candidate_hits.items()},
            **{f'context_recall_at_{k}': _ratio(value, len(evidence_cases)) for k, value in evidence_context_hits.items()},
            'context_result_limit': 8,
            'cross_organization_leakage_rate': _ratio(leakage_failures, leakage_runnable),
            'cross_organization_authorized_recall_at_8': _ratio(leakage_authorized_hits, leakage_runnable),
            'cross_organization_runnable_case_count': leakage_runnable,
        },
        'dual_domain': {
            'case_count': len(mixed),
            'runnable_case_count': mixed_runnable,
            'rule_final_recall_at_5': _ratio(mixed_rule_hits, mixed_runnable),
            'evidence_context_recall_at_8': _ratio(mixed_evidence_hits, mixed_runnable),
            'joint_recall': _ratio(mixed_joint_hits, mixed_runnable),
        },
        'citation_metrics': {'source_field_completeness_rate': _ratio(source_complete, source_total), **citation},
        'claim_grounding': workflow_runtime or {'case_count': len(_load(root, '06_claim_grounding.json')), 'status': 'seeded_cases_pending_claim_runtime_eval'},
        'intake_review': workflow_runtime or {'case_count': len(_load(root, '07_intake_and_review_workflow.json')), 'status': 'seeded_cases_pending_workflow_runtime_eval'},
        'diagnostics': {'rule_cases': rule_rows, 'negative_cases': negative_rows, 'evidence_cases': evidence_rows, 'leakage_cases': leakage_rows, 'mixed_cases': mixed_rows},
    }


def markdown(report):
    lines = ['# Phase 11 Formal Evaluation', '', f"evaluation_scope: {report['evaluation_scope']}", f"evaluation_contract_version: {report['evaluation_contract_version']}", '', '## Runtime Environment']
    lines.extend(f'- {key}: {value}' for key, value in report['runtime_environment']['embedding'].items())
    lines.extend(['', '## RAG Metrics'])
    for group in ('rule_rag', 'user_evidence_rag', 'dual_domain', 'citation_metrics'):
        lines.append(f'### {group}')
        lines.extend(f'- {key}: {value}' for key, value in report[group].items())
    lines.extend(['', '## Failure Reasons'])
    for group in ('rule_cases', 'evidence_cases'):
        values = Counter(item.get('failure_reason') or 'hit' for item in report['diagnostics'][group])
        lines.append(f'- {group}: {dict(sorted(values.items()))}')
    lines.extend(['', '## Claim and Workflow Runtime Metrics'])
    workflow = report['intake_review']
    if 'reviewer_execution' in workflow:
        lines.append(f"- claim_case_count: {workflow['claim_case_count']}")
        for group in ('reviewer_execution', 'review_grill_execution', 'intake_execution'):
            lines.append(f'### {group}')
            lines.extend(f'- {key}: {value}' for key, value in workflow[group].items())
    else:
        lines.append(f"- workflow_status: {workflow['status']}")
    return '\n'.join(lines) + '\n'
