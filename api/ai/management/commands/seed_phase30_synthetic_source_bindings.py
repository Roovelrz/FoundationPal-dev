import json
from datetime import date
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from ai.ingestion import create_resource_with_chunks
from orgs.models import Organization, OrgUser
from proposals.models import Proposal


class Command(BaseCommand):
    help = 'Create test-only synthetic source chunks and complete the Phase 3.0 missing binding template.'

    def add_arguments(self, parser):
        parser.add_argument('--binding-file', required=True)
        parser.add_argument('--user-id', required=True, type=int)
        parser.add_argument('--dataset-registry', required=True)

    def handle(self, *args, **options):
        path = Path(options['binding_file'])
        payload = json.loads(path.read_text(encoding='utf-8'))
        user = get_user_model().objects.get(pk=options['user_id'])
        org, _ = Organization.objects.get_or_create(name='Phase30 Synthetic Test Evidence', defaults={'admin': user})
        OrgUser.objects.get_or_create(org=org, user=user, defaults={'role': 'admin'})
        proposal, _ = Proposal.objects.get_or_create(author=user, org=org, content={'meta': {'synthetic_test_fixture': True}})
        for item in payload['cases']:
            if item['status'] != 'pending_human_source_binding':
                continue
            text = ' '.join([
                'Synthetic test fixture only.', 'External evidence key', item['external_id'] + '.',
                'This source exists to exercise retrieval, authorization, provenance and evaluation paths.',
                'It is not user submitted evidence and must never support production decisions.',
            ])
            resource = create_resource_with_chunks(
                type_='team_profile', title=f'Synthetic source {item["external_id"]}', source_url=f'synthetic://phase30/{item["external_id"]}',
                full_text=text, organization_id=str(org.id), proposal_id=proposal.id, knowledge_domain='user_evidence',
            )
            resource.metadata = {**(resource.metadata or {}), 'synthetic_test_fixture': True, 'external_id': item['external_id']}
            resource.save(update_fields=['metadata'])
            chunk = resource.chunks.order_by('chunk_index').first()
            item.update({
                'stable_chunk_id': chunk.stable_chunk_id, 'page_start': chunk.page_start, 'page_end': chunk.page_end,
                'organization_id': str(org.id), 'proposal_id': proposal.id, 'authorization_scope': 'organization',
                'reviewer': 'synthetic_test_generator', 'review_date': str(date.today()), 'status': 'synthetic_test_confirmed',
            })
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        registry = {
            'dataset': 'phase11_dataset_roles', 'synthetic_test_fixture': True,
            'roles': {
                'development': {'source': 'synthetic_test_fixture', 'tuning_allowed': True},
                'frozen': {'source': 'phase11_human_verified', 'tuning_allowed': False},
                'release_holdout': {'source': 'synthetic_test_fixture', 'tuning_allowed': False},
            },
        }
        Path(options['dataset_registry']).write_text(json.dumps(registry, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'phase30_synthetic_source_bindings_complete:{len(payload["cases"])}'))
