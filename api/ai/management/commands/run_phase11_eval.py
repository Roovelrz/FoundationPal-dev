import json
from pathlib import Path

from django.core.management.base import BaseCommand

from ai.phase11_eval import run_phase11_small_eval


class Command(BaseCommand):
    help = 'Run reproducible Phase 11 small evaluation without changing embeddings.'

    def add_arguments(self, parser):
        parser.add_argument('--output-dir', default='reports')

    def handle(self, *args, **options):
        report = run_phase11_small_eval()
        output = Path(options['output_dir'])
        output.mkdir(parents=True, exist_ok=True)
        for key in ('rule_rag', 'user_evidence_rag', 'intake_grill', 'end_to_end'):
            (output / f'phase11-{key}.json').write_text(json.dumps(report[key], ensure_ascii=False, indent=2), encoding='utf-8')
        (output / 'phase11-summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS('phase11_small_eval_complete'))
