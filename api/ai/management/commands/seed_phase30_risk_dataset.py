import json
from pathlib import Path

from django.core.management.base import BaseCommand

from ai.reviewing import IMPLEMENTED_REVIEW_CODES


class Command(BaseCommand):
    help = 'Generate the Phase 3.0 development and frozen risk-fixture matrix.'

    def add_arguments(self, parser):
        parser.add_argument('--output', required=True)

    def handle(self, *args, **options):
        rows = []
        targets = {'development': {'positive': 5, 'near_negative': 5, 'boundary': 3}, 'frozen': {'positive': 10, 'near_negative': 10, 'boundary': 5}}
        for code in sorted(IMPLEMENTED_REVIEW_CODES):
            for split, counts in targets.items():
                for kind, count in counts.items():
                    rows.extend({'case_id': f'{split}:{code}:{kind}:{index:03d}', 'split': split, 'issue_code': code, 'kind': kind, 'provenance': 'developer_authored_fixture'} for index in range(1, count + 1))
        payload = {'dataset': 'phase30_reviewer_risk_matrix', 'cases': rows}
        Path(options['output']).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'phase30_risk_dataset_complete:{len(rows)}'))
