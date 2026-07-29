import json
from pathlib import Path

from django.core.management.base import BaseCommand
from ai.phase11_formal_eval import markdown, run_formal_eval


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--input-dir', required=True)
        parser.add_argument('--output-dir', default='reports')
        parser.add_argument('--mapping-kind-prefix', default='')
    def handle(self, *args, **options):
        output = Path(options['output_dir']); output.mkdir(parents=True, exist_ok=True)
        report = run_formal_eval(options['input_dir'], output / 'phase11-claim-workflow.json', options['mapping_kind_prefix'])
        (output / 'phase11-formal-eval.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        (output / 'phase11-formal-eval.md').write_text(markdown(report), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS('phase11_formal_eval_complete'))
