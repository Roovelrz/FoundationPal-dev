import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ai.models import Phase11SeedMap, UserEvidence


class Command(BaseCommand):
    help = 'Export public-AMR evidence bindings from imported isolated evaluation fixtures.'

    def add_arguments(self, parser):
        parser.add_argument('--input-dir', required=True)
        parser.add_argument('--output', required=True)
        parser.add_argument('--mapping-kind-prefix', default='phase30_public_')

    def handle(self, *args, **options):
        root = Path(options['input_dir'])
        cases = json.loads((root / '02_user_evidence_grounding.json').read_text(encoding='utf-8'))['cases']
        prefix = options['mapping_kind_prefix']
        mapping = {
            row.external_id: row.target_id
            for row in Phase11SeedMap.objects.filter(kind=f'{prefix}user_evidence')
        }
        rows = []
        for case in cases:
            external_id = case['user_evidence_ids'][0]
            evidence_id = mapping.get(external_id)
            if evidence_id is None:
                raise CommandError(f'missing_public_evidence_mapping:{external_id}')
            evidence = UserEvidence.objects.select_related('resource', 'chunk').get(pk=evidence_id)
            rows.append({
                'external_id': external_id,
                'stable_chunk_id': evidence.chunk.stable_chunk_id,
                'page_start': evidence.chunk.page_start,
                'page_end': evidence.chunk.page_end,
                'organization_id': evidence.resource.organization_id,
                'proposal_id': evidence.resource.proposal_id,
                'authorization_scope': 'organization',
                'reviewer': 'roovel',
                'review_date': '2026-07-28',
                'status': 'human_confirmed',
                'source_type': 'public_amr_pdf',
            })
        payload = {'dataset': 'phase30_public_amr_original_evidence_bindings', 'cases': rows}
        output = Path(options['output'])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'phase30_public_amr_bindings_exported:{len(rows)}'))
