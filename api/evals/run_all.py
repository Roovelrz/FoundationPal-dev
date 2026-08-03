'''Read-only aggregation for committed FoundationPal evaluation reports.'''

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULT_FILES = {
    'e2e_baseline': Path('api/reports/eval-baseline.json'),
    'phase10_auto': Path('api/reports/phase10-auto-eval.json'),
    'phase10_reference': Path('api/reports/phase10-eval.json'),
    'intake_contract': Path('api/reports/phase40_p03_intake_eval.json'),
    'p0_reference': Path('api/reports/phase40_p0v5_eval/phase11-formal-eval.json'),
    'p1_strict': Path('api/reports/phase40_p1_holdout_eval/phase40-p1-formal-eval.json'),
    'rag_initial_candidates': Path('api/reports/rag-initial-candidates.json'),
    'rag_judge_sample': Path('api/reports/rag-judge-sample.json'),
    'rag_regression': Path('api/reports/rag-regression.json'),
}
SOURCE_LABELS = {
    'e2e_baseline': 'Eval baseline',
    'phase10_auto': 'Historical Phase 10 automatic report',
    'phase10_reference': 'Historical Phase 10 reference report',
    'intake_contract': 'Phase 40 P03 intake contract',
    'p0_reference': 'Phase 40 P0v5 formal report',
    'p1_strict': 'Phase 40 P1 strict holdout',
    'rag_initial_candidates': 'RAG initial candidates',
    'rag_judge_sample': 'Historical RAG judge sample',
    'rag_regression': 'RAG regression',
}
METADATA_PREFIXES = (
    'runtime_environment.',
    'model.',
    'evaluation_scope',
    'evaluation_contract_version',
    'mapping_kind_prefix',
    'frozen_case_set',
    'scope.organization_id',
    'fixture',
)
KEY_METRIC_IDS = (
    'workflow.routing_accuracy',
    'retrieval.recall_at_5',
    'retrieval.dual_domain.joint_recall',
    'grounding.claim_support_rate',
    'isolation.cross_organization_leakage_rate',
)
KNOWN_GAPS = [
    {
        'metric': 'reviewer.risk_recall',
        'reason': 'No committed result currently reports reviewer risk recall on implemented risk types.',
    },
    {
        'metric': 'grounding.numeric_conflict_count',
        'reason': 'No committed result currently reports numeric-conflict evaluation output.',
    },
    {
        'metric': 'workflow.grill_completion_rate',
        'reason': 'No committed result currently reports Grill completion rate.',
    },
    {
        'metric': 'workflow.release_signoff_pass_rate',
        'reason': 'No committed result currently reports a standalone release-signoff pass rate.',
    },
]


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        print(f'Skipped missing result: {path.relative_to(PROJECT_ROOT)}')
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def value_at(data: dict[str, Any], path: str) -> Any:
    value: Any = data
    for key in path.split('.'):
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def flatten_values(value: Any, prefix: str = '') -> dict[str, Any]:
    if isinstance(value, dict):
        flattened: dict[str, Any] = {}
        for key, item in value.items():
            next_prefix = f'{prefix}.{key}' if prefix else key
            flattened.update(flatten_values(item, next_prefix))
        return flattened
    if isinstance(value, list):
        return {f'{prefix}.count': len(value)} if prefix else {}
    if isinstance(value, (bool, int, float)):
        return {prefix: value}
    if isinstance(value, str) and prefix.endswith('status'):
        return {prefix: value}
    return {}


def is_metric_path(path: str) -> bool:
    return not any(path == prefix.rstrip('.') or path.startswith(prefix) for prefix in METADATA_PREFIXES)


def add_metric(
    bucket: list[dict[str, Any]],
    metric_id: str,
    label: str,
    value: Any,
    scope: str,
    source: str,
    source_field: str,
) -> None:
    if value is not None:
        bucket.append({
            'id': metric_id,
            'label': label,
            'value': value,
            'scope': scope,
            'source': source,
            'source_field': source_field,
        })


def add_from_path(
    bucket: list[dict[str, Any]],
    data: dict[str, Any] | None,
    metric_id: str,
    label: str,
    scope: str,
    source: str,
    source_field: str,
) -> None:
    if data is not None:
        add_metric(bucket, metric_id, label, value_at(data, source_field), scope, source, source_field)


def collect_normalized_metrics(reports: dict[str, dict[str, Any] | None]) -> dict[str, list[dict[str, Any]]]:
    metrics = {name: [] for name in ('retrieval', 'grounding', 'isolation', 'reviewer', 'workflow', 'e2e')}
    strict = reports['p1_strict']
    if strict is not None:
        def strict_metric(group: str, metric_id: str, label: str, scope: str, source_field: str) -> None:
            add_from_path(
                metrics[group],
                strict,
                metric_id,
                label,
                scope,
                'p1_strict',
                source_field,
            )

        rule_scope = 'P1 strict rule retrieval'
        for suffix, label in (
            ('candidate_recall_at_20', 'Rule Candidate Recall@20'),
            ('candidate_recall_at_40', 'Rule Candidate Recall@40'),
        ):
            strict_metric(
                'retrieval',
                f'retrieval.rule.{suffix}',
                label,
                rule_scope,
                f'rule_rag.{suffix}',
            )
        evidence_scope = 'P1 strict user-evidence retrieval'
        for suffix, label in (
            ('candidate_recall_at_20', 'User Evidence Candidate Recall@20'),
            ('context_recall_at_1', 'User Evidence Context Recall@1'),
            ('context_recall_at_3', 'User Evidence Context Recall@3'),
            ('context_recall_at_5', 'User Evidence Context Recall@5'),
            ('context_recall_at_8', 'User Evidence Context Recall@8'),
            ('context_result_limit', 'User Evidence Context Result Limit'),
        ):
            strict_metric(
                'retrieval',
                f'retrieval.user_evidence.{suffix}',
                label,
                evidence_scope,
                f'user_evidence_rag.{suffix}',
            )
        dual_scope = 'P1 strict mixed-domain cases'
        for suffix, label in (
            ('rule_final_recall_at_5', 'Dual-Domain Rule Final Recall@5'),
            ('evidence_context_recall_at_8', 'Dual-Domain Evidence Context Recall@8'),
            ('joint_recall', 'Dual-Domain Joint Recall'),
        ):
            strict_metric(
                'retrieval',
                f'retrieval.dual_domain.{suffix}',
                label,
                dual_scope,
                f'dual_domain.{suffix}',
            )
        for metric_id, label, source_field in (
            ('retrieval.recall_at_1', 'Rule Final Recall@1', 'rule_rag.final_recall_at_1'),
            ('retrieval.recall_at_3', 'Rule Final Recall@3', 'rule_rag.final_recall_at_3'),
            ('retrieval.recall_at_5', 'Rule Final Recall@5', 'rule_rag.final_recall_at_5'),
        ):
            strict_metric('retrieval', metric_id, label, rule_scope, source_field)
        grounding_scope = 'P1 strict citation labels'
        for metric_id, label, source_field in (
            ('grounding.claim_support_rate', 'Claim Support Rate', 'citation_metrics.citation_entailment_rate'),
            (
                'grounding.citation_source_field_completeness_rate',
                'Citation Source Field Completeness Rate',
                'citation_metrics.source_field_completeness_rate',
            ),
            (
                'grounding.unsupported_claim_count',
                'Unsupported Claim Count',
                'citation_metrics.citation_label_counts.unsupported',
            ),
            (
                'grounding.citation_evaluable_case_count',
                'Citation Evaluable Case Count',
                'citation_metrics.citation_evaluable_case_count',
            ),
        ):
            strict_metric('grounding', metric_id, label, grounding_scope, source_field)
        unsupported = value_at(strict, 'citation_metrics.citation_label_counts.unsupported')
        evaluable = value_at(strict, 'citation_metrics.citation_evaluable_case_count')
        if isinstance(unsupported, (int, float)) and isinstance(evaluable, (int, float)) and evaluable:
            add_metric(
                metrics['grounding'],
                'grounding.unsupported_claim_rate',
                'Unsupported Claim Rate',
                unsupported / evaluable,
                grounding_scope,
                'p1_strict',
                'citation_label_counts.unsupported / citation_evaluable_case_count',
            )
        isolation_scope = 'P1 strict leakage cases'
        for metric_id, label, scope, source_field in (
            (
                'isolation.cross_organization_leakage_rate',
                'Cross-Organization Leakage Rate',
                isolation_scope,
                'user_evidence_rag.cross_organization_leakage_rate',
            ),
            (
                'isolation.authorized_recall_at_8',
                'Authorized Evidence Recall@8',
                isolation_scope,
                'user_evidence_rag.cross_organization_authorized_recall_at_8',
            ),
            (
                'isolation.runnable_case_count',
                'Cross-Organization Runnable Case Count',
                isolation_scope,
                'user_evidence_rag.cross_organization_runnable_case_count',
            ),
            (
                'isolation.holdout_valid',
                'P1 Holdout Validation',
                'P1 strict holdout validation',
                'p1_holdout_validation.valid',
            ),
            (
                'isolation.exact_query_leak_count',
                'Exact Query Leak Count',
                'P1 strict holdout validation',
                'p1_holdout_validation.exact_query_leaks.count',
            ),
            (
                'isolation.eight_character_query_leak_count',
                'Eight-Character Query Leak Count',
                'P1 strict holdout validation',
                'p1_holdout_validation.eight_character_query_leaks.count',
            ),
        ):
            strict_metric('isolation', metric_id, label, scope, source_field)

    intake = reports['intake_contract']
    if intake is not None:
        intake_scope = 'Phase 40 P03 intake contract'
        for field, label in (
            ('fixture_case_count', 'Intake Fixture Case Count'),
            ('routing_accuracy', 'Intake Routing Accuracy'),
            ('question_budget_accuracy', 'Question Budget Accuracy'),
            ('remaining_discrepancy_count', 'Remaining Intake Discrepancy Count'),
        ):
            add_from_path(
                metrics['workflow'],
                intake,
                f'workflow.{field}',
                label,
                intake_scope,
                'intake_contract',
                field,
            )

    baseline = reports['e2e_baseline']
    if baseline is not None:
        total = len(baseline.get('cases') or [])
        failures = baseline.get('failure_count')
        if isinstance(failures, (int, float)) and total:
            successful = total - failures
            baseline_scope = 'Existing eval baseline cases'
            for metric_id, label, value, source_field in (
                ('e2e.total_tasks', 'Total Eval Cases', total, 'cases.count'),
                ('e2e.successful_tasks', 'Passed Cases', successful, 'cases.count - failure_count'),
                ('e2e.failed_tasks', 'Failed Cases', failures, 'failure_count'),
                (
                    'e2e.task_success_rate',
                    'End-to-End Task Success Rate',
                    successful / total,
                    'cases.count and failure_count',
                ),
            ):
                add_metric(
                    metrics['e2e'],
                    metric_id,
                    label,
                    value,
                    baseline_scope,
                    'e2e_baseline',
                    source_field,
                )
    return metrics


def build_summary(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    reports: dict[str, dict[str, Any] | None] = {}
    loaded_files: list[dict[str, str]] = []
    missing_files: list[dict[str, str]] = []
    for name, relative_path in RESULT_FILES.items():
        path = root / relative_path
        reports[name] = load_json(path)
        entry = {'name': name, 'path': str(relative_path).replace('\\', '/')}
        if reports[name] is None:
            missing_files.append(entry)
        else:
            loaded_files.append(entry)

    source_report_metrics: dict[str, list[dict[str, Any]]] = {}
    for name, report in reports.items():
        if report is None:
            continue
        source_report_metrics[name] = [
            {'field': field, 'value': value}
            for field, value in sorted(flatten_values(report).items())
            if is_metric_path(field)
        ]

    metrics = collect_normalized_metrics(reports)
    normalized_by_id = {
        metric['id']: metric
        for values in metrics.values()
        for metric in values
    }
    key_metrics = [normalized_by_id[metric_id] for metric_id in KEY_METRIC_IDS if metric_id in normalized_by_id]
    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'key_metrics': key_metrics,
        'metrics': metrics,
        'source_report_metrics': source_report_metrics,
        'coverage': {
            'loaded_result_files': loaded_files,
            'missing_result_files': missing_files,
            'not_reported_metrics': KNOWN_GAPS,
        },
    }


def format_value(value: Any, metric_id: str = '') -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        rate_words = ('rate', 'recall', 'accuracy', 'correctness', 'faithfulness', 'coverage', 'entailment')
        if any(word in metric_id for word in rate_words):
            return f'{value * 100:.2f}%'
        return str(value)
    return str(value)


def append_normalized_table(
    lines: list[str],
    metrics: list[dict[str, Any]],
    include_metadata: bool,
) -> None:
    if not metrics:
        lines.append('No current output was found for this group.')
        return
    if include_metadata:
        lines.extend(['| Metric | Value | Scope | Source |', '|---|---:|---|---|'])
        for metric in metrics:
            lines.append('| {label} | {value} | {scope} | {source} |'.format(
                label=metric['label'],
                value=format_value(metric['value'], metric['id']),
                scope=metric['scope'],
                source=SOURCE_LABELS[metric['source']],
            ))
        return
    lines.extend(['| Metric | Value |', '|---|---:|'])
    for metric in metrics:
        lines.append('| {label} | {value} |'.format(
            label=metric['label'],
            value=format_value(metric['value'], metric['id']),
        ))


def write_summary_markdown(
    summary: dict[str, Any],
    output_path: Path,
    include_metadata: bool = False,
) -> None:
    all_metrics_heading = (
        '## All Existing Source Metrics'
        if include_metadata
        else '## All Existing Report Metrics'
    )
    lines = [
        '# FoundationPal Agent Evaluation Summary',
        '',
        'This read-only summary loads committed result files. Key metrics appear first; '
        'all current report metrics remain below with their original field names.',
        '',
        '## Key Metrics',
    ]
    append_normalized_table(lines, summary['key_metrics'], include_metadata)
    lines.extend(['', '## Normalized Metrics'])
    for group in ('retrieval', 'grounding', 'isolation', 'reviewer', 'workflow', 'e2e'):
        lines.extend(['', '### ' + group.replace('_', ' ').title()])
        append_normalized_table(lines, summary['metrics'][group], include_metadata)

    lines.extend(['', all_metrics_heading])
    for name, metrics in summary['source_report_metrics'].items():
        lines.extend(['', f'### {SOURCE_LABELS[name]}'])
        if include_metadata:
            lines.append(f'Source: `{RESULT_FILES[name].as_posix()}`')
            lines.extend(['', '| Source field | Value |', '|---|---:|'])
        else:
            lines.extend(['| Metric field | Value |', '|---|---:|'])
        for metric in metrics:
            lines.append('| {field} | {value} |'.format(
                field=metric['field'],
                value=format_value(metric['value'], metric['field']),
            ))

    coverage = summary['coverage']
    lines.extend(['', '## Coverage', '', '### Loaded result files'])
    lines.extend('- ' + item['path'] for item in coverage['loaded_result_files'])
    lines.extend(['', '### Missing result files'])
    if coverage['missing_result_files']:
        lines.extend('- ' + item['path'] for item in coverage['missing_result_files'])
    else:
        lines.append('- None')
    lines.extend(['', '### Metrics not reported by current outputs'])
    lines.extend('- ' + item['metric'] + ': ' + item['reason'] for item in coverage['not_reported_metrics'])
    output_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def write_summary_json(summary: dict[str, Any], output_path: Path) -> None:
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main() -> dict[str, Any]:
    summary = build_summary()
    output_dir = PROJECT_ROOT / 'api' / 'evals' / 'reports'
    output_dir.mkdir(parents=True, exist_ok=True)
    write_summary_json(summary, output_dir / 'summary.json')
    write_summary_markdown(summary, output_dir / 'summary.md')
    write_summary_markdown(
        summary,
        output_dir / 'summary.local.md',
        include_metadata=True,
    )
    print(f'Wrote {output_dir.relative_to(PROJECT_ROOT).as_posix()}/summary.json')
    print(f'Wrote {output_dir.relative_to(PROJECT_ROOT).as_posix()}/summary.md')
    print(f'Wrote {output_dir.relative_to(PROJECT_ROOT).as_posix()}/summary.local.md')
    return summary


if __name__ == '__main__':
    main()
