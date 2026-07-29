import json
from pathlib import Path

from django.core.management.base import BaseCommand

from ai.phase40_p03 import evaluate_intake_contract


class Command(BaseCommand):
    help = 'Evaluate the frozen P0-3 Intake routing contract without database writes.'

    def add_arguments(self, parser):
        parser.add_argument('--input-dir', required=True)
        parser.add_argument('--output', required=True)

    def handle(self, *args, **options):
        source = Path(options['input_dir']) / '07_intake_and_review_workflow.json'
        cases = json.loads(source.read_text(encoding='utf-8'))['cases']
        intake_cases = [item for item in cases if item['case_id'].startswith('intake:')]
        report = evaluate_intake_contract(intake_cases)
        report['evaluation_scope'] = 'phase40_p03_intake_contract'
        report['fixture'] = str(source)
        output = Path(options['output'])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS('phase40_p03_intake_eval_complete'))
