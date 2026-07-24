import hashlib
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ai.observability import build_phase10_report, markdown_report


class Command(BaseCommand):
    help = 'Write the Phase 10 report from persisted workflow, evidence, and tool records.'

    def add_arguments(self, parser):
        parser.add_argument('--output-dir', default='reports')
        parser.add_argument('--organization-id', default='')
        parser.add_argument('--rag-regression')
        parser.add_argument('--frozen-cases')

    def handle(self, *args, **options):
        rag_regression = None
        if options['rag_regression']:
            path = Path(options['rag_regression'])
            if not path.is_file():
                raise CommandError(f'rag_regression_not_found: {path}')
            rag_regression = json.loads(path.read_text(encoding='utf-8'))
        frozen_case_set = None
        if options['frozen_cases']:
            path = Path(options['frozen_cases'])
            if not path.is_file():
                raise CommandError(f'frozen_cases_not_found: {path}')
            payload = path.read_bytes()
            loaded = json.loads(payload.decode('utf-8'))
            cases = loaded.get('cases', loaded) if isinstance(loaded, dict) else loaded
            frozen_case_set = {'path': str(path), 'count': len(cases), 'sha256': hashlib.sha256(payload).hexdigest()}
        report = build_phase10_report(
            organization_id=options['organization_id'],
            rag_regression=rag_regression,
            frozen_case_set=frozen_case_set,
        )
        output_dir = Path(options['output_dir'])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / 'phase10-eval.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        (output_dir / 'phase10-eval.md').write_text(markdown_report(report), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'phase10_report_complete: {report["scope"]["run_count"]} runs'))
