import json
from pathlib import Path


REQUIRED = {'case_id', 'domain', 'query', 'answer_state', 'annotation_status'}
DOMAINS = {'grant_rule', 'user_evidence', 'mixed'}
ANSWER_STATES = {'answerable', 'no_applicable_rule', 'missing_evidence'}


def load_frozen_cases(path):
    loaded = json.loads(Path(path).read_text(encoding='utf-8'))
    cases = loaded.get('cases') if isinstance(loaded, dict) else loaded
    if not isinstance(cases, list):
        raise ValueError('frozen_eval_cases_invalid')
    failures = []
    accepted = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or not REQUIRED.issubset(case):
            failures.append({'index': index, 'error': 'case_schema_invalid'})
            continue
        if case['domain'] not in DOMAINS or case['answer_state'] not in ANSWER_STATES:
            failures.append({'case_id': case.get('case_id'), 'error': 'domain_or_answer_state_invalid'})
            continue
        if case['annotation_status'] != 'human_confirmed':
            if case['annotation_status'] == 'pending_human_review' and str(case.get('annotation_notes') or '').strip():
                failures.append({'case_id': case['case_id'], 'error': 'excluded_pending_human_review', 'reason': case['annotation_notes']})
            else:
                failures.append({'case_id': case['case_id'], 'error': 'annotation_not_human_confirmed'})
            continue
        if case['domain'] in {'grant_rule', 'mixed'} and case['answer_state'] == 'answerable' and not case.get('requirement_ids') and not case.get('gold_chunk_ids'):
            failures.append({'case_id': case['case_id'], 'error': 'rule_trace_labels_missing'})
            continue
        if case['domain'] in {'user_evidence', 'mixed'} and case['answer_state'] == 'answerable' and not case.get('user_evidence_ids') and not case.get('gold_chunk_ids'):
            failures.append({'case_id': case['case_id'], 'error': 'user_evidence_trace_labels_missing'})
            continue
        accepted.append(case)
    return accepted, failures


def frozen_eval_report(path):
    accepted, failures = load_frozen_cases(path)
    by_domain = {domain: sum(item['domain'] == domain for item in accepted) for domain in DOMAINS}
    by_answer_state = {state: sum(item['answer_state'] == state for item in accepted) for state in ANSWER_STATES}
    return {
        'evaluation_scope': 'frozen_human_annotated_only',
        'embedding_comparison': 'unchanged_embedding_only',
        'accepted_case_count': len(accepted),
        'rejected_case_count': len(failures),
        'domain_counts': by_domain,
        'answer_state_counts': by_answer_state,
        'excluded_pending_review_count': sum(item.get('error') == 'excluded_pending_human_review' for item in failures),
        'ready_for_formal_comparison': len(accepted) >= 162 and by_domain['grant_rule'] and by_domain['user_evidence'] and all(item.get('error') == 'excluded_pending_human_review' for item in failures) and len(failures) <= 3,
        'rejections': failures,
    }
