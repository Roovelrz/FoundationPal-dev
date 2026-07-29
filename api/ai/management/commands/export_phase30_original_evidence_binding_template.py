import json
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Export the unresolved Phase 3.0 original-evidence binding template without inventing source chunks.'

    def add_arguments(self, parser):
        parser.add_argument('--confirmation-report', required=True)
        parser.add_argument('--output', required=True)

    def handle(self, *args, **options):
        report = json.loads(Path(options['confirmation_report']).read_text(encoding='utf-8'))
        rows = []
        for item in report['pending_human_confirmation']['phase_1_original_source_bindings']:
            rows.append({
                'external_id': item['external_id'],
                'case_id': item['case_id'],
                'stable_chunk_id': '',
                'page_start': None,
                'page_end': None,
                'organization_id': '',
                'proposal_id': None,
                'authorization_scope': '',
                'reviewer': '',
                'review_date': '',
                'status': 'pending_human_source_binding',
            })
        payload = {'dataset': 'phase11_original_evidence_bindings', 'cases': rows}
        output = Path(options['output'])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'phase30_original_evidence_binding_template_exported:{len(rows)}'))
