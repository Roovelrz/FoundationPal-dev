import json
from pathlib import Path

from django.core.management import BaseCommand, CommandError
from django.test.runner import DiscoverRunner


CASES = [
    {'id': 'happy_path', 'input': 'anonymous grant brief', 'expected_sections': 3, 'expected_database_state': 'approved_and_exported'},
    {'id': 'invalid_planner', 'input': 'missing section_key', 'expected_sections': 0, 'expected_database_state': 'unchanged'},
    {'id': 'writer_failure', 'input': 'provider exception', 'expected_sections': 1, 'expected_database_state': 'draft_preserved'},
    {'id': 'reviewer_rewrite', 'input': 'unknown decision', 'expected_sections': 1, 'expected_database_state': 'not_promoted'},
    {'id': 'export_failure', 'input': 'unapproved proposal', 'expected_sections': 0, 'expected_database_state': 'no_export_job'},
]


class Command(BaseCommand):
    help = 'Run the fixed eval baseline and write JSON plus Markdown reports.'

    def add_arguments(self, parser):
        parser.add_argument('--output-dir', default='reports')

    def handle(self, *args, **options):
        output_dir = Path(options['output_dir'])
        output_dir.mkdir(parents=True, exist_ok=True)
        failures = DiscoverRunner(verbosity=0).run_tests([
            'ai.tests.test_eval_baseline',
            'ai.tests.test_main_workflow_e2e',
        ])
        report = {'cases': CASES, 'passed': failures == 0, 'failure_count': failures}
        (output_dir / 'eval-baseline.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        markdown = '# Eval Baseline\n\n' + '\n'.join(
            f'- {case["id"]}: {case["expected_database_state"]}' for case in CASES
        ) + f'\n\nResult: {"passed" if failures == 0 else "failed"}\n'
        (output_dir / 'eval-baseline.md').write_text(markdown, encoding='utf-8')
        self.stdout.write(json.dumps(report, ensure_ascii=False))
        if failures:
            raise CommandError('eval baseline failed')
