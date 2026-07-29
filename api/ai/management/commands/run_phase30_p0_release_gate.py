import json
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Evaluate Phase 3.0 P0 release prerequisites without converting blocked items into approvals.'

    def add_arguments(self, parser):
        parser.add_argument('--reports-dir', required=True)
        parser.add_argument('--output-json', required=True)
        parser.add_argument('--output-md', required=True)
        parser.add_argument('--formal-report', default='phase11-formal-eval.json')
        parser.add_argument('--readiness-report', default='phase11-bge-corpus-readiness.json')

    def handle(self, *args, **options):
        reports = Path(options['reports_dir'])
        formal = json.loads((reports / options['formal_report']).read_text(encoding='utf-8'))
        readiness = json.loads((reports / options['readiness_report']).read_text(encoding='utf-8'))
        embedding = formal['runtime_environment']['embedding']
        checks = {
            'bge_backend': embedding.get('backend') == 'bge',
            'bge_model': embedding.get('model') == 'bge-base-zh-v1.5',
            'bge_dimension': embedding.get('dim') == 768,
            'unpublished_pack_safety': formal['rule_rag']['unpublished_pack_safety_block_rate'] == 1,
            'citation_entailment_labels': formal['citation_metrics']['citation_entailment_status'].startswith('measured'),
            'user_evidence_bge': readiness['user_evidence_semantic_baseline_status'] == 'ready',
            'dual_domain_bge': embedding.get('backend') == 'bge' and formal['dual_domain']['runnable_case_count'] > 0,
            'no_synthetic_test_fixtures': readiness.get('synthetic_test_fixture_count', 0) == 0 and formal['citation_metrics'].get('citation_annotation_level') != 'synthetic_test_developer_review',
        }
        payload = {
            'phase': '3.0_p0_release_gate',
            'release_ready': all(checks.values()),
            'checks': checks,
            'blocked_checks': [name for name, passed in checks.items() if not passed],
            'note': 'Citation labels are developer initial review and still require business sign-off before production release.',
        }
        output_json = Path(options['output_json'])
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        lines = ['# 3.0 P0 发布门禁', '', f"- release_ready: {payload['release_ready']}"]
        lines.extend(f'- {name}: {passed}' for name, passed in checks.items())
        lines.extend(['', '## 阻断项'])
        lines.extend(f'- {name}' for name in payload['blocked_checks'])
        lines.extend(['', payload['note']])
        Path(options['output_md']).write_text('\n'.join(lines) + '\n', encoding='utf-8')
        self.stdout.write(self.style.SUCCESS('phase30_p0_release_gate_complete'))
