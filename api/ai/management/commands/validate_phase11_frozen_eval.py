import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ai.phase11_frozen import frozen_eval_report


class Command(BaseCommand):
    help = 'Validate the Phase 11 human-annotated frozen evaluation set without changing embeddings.'

    def add_arguments(self, parser):
        parser.add_argument('--dataset', required=True)
        parser.add_argument('--output', default='reports/phase11-frozen-validation.json')

    def handle(self, *args, **options):
        report = frozen_eval_report(options['dataset'])
        output = Path(options['output'])
        if not output.is_absolute():
            output = Path.cwd() / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        if not report['ready_for_formal_comparison']:
            raise CommandError('phase11_frozen_eval_not_ready')
        self.stdout.write(self.style.SUCCESS('phase11_frozen_eval_ready'))
