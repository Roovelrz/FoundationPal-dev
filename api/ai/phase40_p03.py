from types import SimpleNamespace

from .intake import build_policy


def evaluate_intake_contract(cases):
    rows = []
    route_hits = budget_hits = 0
    for case in cases:
        profile = SimpleNamespace(
            task_mode=case['task_mode'],
            quality_level=case['quality_level'],
            rule_readiness=case['rule_readiness'],
            content_maturity=case['content_maturity'],
            evidence_readiness=case['evidence_readiness'],
        )
        policy = build_policy(profile)
        route_match = policy['grill_mode'] == case['expected_grill_mode']
        budget_match = policy['question_budget'] == case['expected_max_questions']
        route_hits += route_match
        budget_hits += budget_match
        rows.append({
            'case_id': case['case_id'],
            'expected_grill_mode': case['expected_grill_mode'],
            'actual_grill_mode': policy['grill_mode'],
            'expected_max_questions': case['expected_max_questions'],
            'actual_question_budget': policy['question_budget'],
            'route_match': route_match,
            'question_budget_match': budget_match,
            'discrepancy_category': None if route_match and budget_match else 'implementation_error',
        })
    count = len(rows)
    return {
        'fixture_case_count': count,
        'routing_accuracy': round(route_hits / count, 4) if count else None,
        'question_budget_accuracy': round(budget_hits / count, 4) if count else None,
        'remaining_discrepancy_count': sum(not (item['route_match'] and item['question_budget_match']) for item in rows),
        'diagnostics': rows,
    }
