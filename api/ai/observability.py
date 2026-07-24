from __future__ import annotations

from django.conf import settings

from .models import AIMetric, EvidenceUsage, ToolInvocation, WorkflowRun


def ratio(numerator: int, denominator: int):
    return round(numerator / denominator, 4) if denominator else None


def build_phase10_report(*, organization_id='', rag_regression=None, frozen_case_set=None):
    runs = WorkflowRun.objects.all().order_by('created_at')
    if organization_id:
        runs = runs.filter(org_id=organization_id)
    run_list = list(runs)
    evidence = EvidenceUsage.objects.filter(workflow_run__in=run_list)
    tools = ToolInvocation.objects.filter(workflow_run__in=run_list)
    metrics = AIMetric.objects.filter(org_id=organization_id) if organization_id else AIMetric.objects.all()

    used_evidence = evidence.filter(used_in_prompt=True)
    cited_evidence = used_evidence.filter(cited_by_model=True)
    min_similarity = float(getattr(settings, 'AI_EVAL_MIN_EVIDENCE_SIMILARITY', 0.0))
    invalid_citations = sum(item.similarity_score < min_similarity for item in cited_evidence)
    tool_count = tools.count()
    successful_tools = tools.filter(status='done').count()
    retried_tools = tools.filter(replay_count__gt=0)
    rejected_tools = tools.filter(status='rejected')

    architecture = {}
    for name in ('sequential', 'langgraph_single', 'multi_agent'):
        group = [run for run in run_list if run.architecture == name]
        reviewer_runs = [run for run in group if any(item.get('agent') == 'reviewer' for item in run.handoffs_json)]
        completed = [run for run in group if run.status in {'completed', 'awaiting_human_approval'}]
        durations = [
            (run.completed_at - run.created_at).total_seconds() * 1000
            for run in group if run.completed_at is not None
        ]
        architecture[name] = {
            'run_count': len(group),
            'workflow_task_success_rate': ratio(len(completed), len(group)),
            'reviewer_regression_rate': ratio(sum(run.revision_count > 0 for run in reviewer_runs), len(reviewer_runs)),
            'average_fallback_count': round(sum(bool(run.fallback_mode) for run in group) / len(group), 4) if group else None,
            'human_intervention_rate': ratio(sum(run.fallback_mode == 'human' for run in group), len(group)),
            'checkpoint_recovery_success_rate': ratio(
                sum(run.status == 'completed' for run in group if run.resumed_from_checkpoint),
                sum(run.resumed_from_checkpoint for run in group),
            ),
            'average_end_to_end_ms': round(sum(durations) / len(durations), 2) if durations else None,
        }

    report = {
        'scope': {'organization_id': organization_id, 'run_count': len(run_list)},
        'frozen_case_set': frozen_case_set,
        'rag': {
            'context_recall_at_k': (rag_regression or {}).get('metrics', {}),
            'no_answer_correctness': None,
            'faithfulness': None,
            'evidence_coverage_rate': ratio(cited_evidence.count(), used_evidence.count()),
            'incorrect_evidence_citation_rate': ratio(invalid_citations, cited_evidence.count()),
            'not_measured': [
                'no_answer_correctness_requires_answer_annotations',
                'faithfulness_requires_claim_level_annotations',
            ],
        },
        'tools': {
            'tool_call_success_rate': ratio(successful_tools, tool_count),
            'authorization_rejection_correctness': ratio(
                rejected_tools.filter(error_code__in={'tool_not_authorized', 'workspace_forbidden'}).count(),
                rejected_tools.count(),
            ),
            'idempotent_retry_success_rate': ratio(
                sum(item.status == 'done' for item in retried_tools), retried_tools.count(),
            ),
            'average_tool_latency_ms': round(
                sum(item.duration_ms for item in tools) / tool_count, 2,
            ) if tool_count else None,
            'not_measured': [] if rejected_tools.exists() else ['authorization_rejection_correctness_requires_rejected_call_audit_rows'],
        },
        'workflow_and_agents': architecture,
        'cost': {
            'estimated_cost_usd': round(sum(item.estimated_cost_usd for item in metrics), 8),
            'token_usage': sum(item.tokens_used for item in metrics),
        },
        'comparison': {
            'architectures': architecture,
            'failure_cases': [
                {
                    'run_id': str(run.run_id),
                    'architecture': run.architecture,
                    'status': run.status,
                    'error': next((item.get('error', '') for item in run.trace_json if item.get('error')), ''),
                }
                for run in run_list if run.status not in {'completed', 'awaiting_human_approval'}
            ],
        },
    }
    return report


def markdown_report(report):
    lines = ['# Phase 10 Eval and Observability Report', '']
    lines.extend([
        f'- Workflow runs: {report["scope"]["run_count"]}',
        f'- Evidence coverage rate: {report["rag"]["evidence_coverage_rate"]}',
        f'- Tool call success rate: {report["tools"]["tool_call_success_rate"]}',
        '',
        '## Architecture comparison',
        '',
        '| Architecture | Runs | Success rate | Human intervention | Average latency ms |',
        '| --- | ---: | ---: | ---: | ---: |',
    ])
    for name, metrics in report['comparison']['architectures'].items():
        lines.append(
            f"| {name} | {metrics['run_count']} | {metrics['workflow_task_success_rate']} | "
            f"{metrics['human_intervention_rate']} | {metrics['average_end_to_end_ms']} |"
        )
    lines.extend(['', '## Not measured', ''])
    lines.extend(f'- {item}' for item in report['rag']['not_measured'] + report['tools']['not_measured'])
    return '\n'.join(lines) + '\n'
