import hashlib
import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ai.ingestion import create_resource_with_chunks
from ai.models import Phase11SeedMap, UserEvidence
from orgs.models import Organization, OrgUser


class Command(BaseCommand):
    help = 'Import verified Phase 11 cross-organization leakage fixtures.'

    def add_arguments(self, parser):
        parser.add_argument('--input-file', required=True)
        parser.add_argument('--user-id', required=True, type=int)
        parser.add_argument('--mapping-kind-prefix', default='')
        parser.add_argument('--source-binding-file')

    @transaction.atomic
    def handle(self, *args, **options):
        user = get_user_model().objects.filter(pk=options['user_id']).first()
        if user is None:
            raise CommandError('seed_owner_not_found')
        cases = json.loads(Path(options['input_file']).read_text(encoding='utf-8'))['cases']
        bindings = {}
        if options['source_binding_file']:
            bindings = {
                item['external_id']: item
                for item in json.loads(Path(options['source_binding_file']).read_text(encoding='utf-8'))['cases']
            }
        prefix = options['mapping_kind_prefix']
        source_hash = hashlib.sha256(json.dumps(cases, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()
        organization_ids = {
            org_id
            for case in cases
            for org_id in (case['authorized_organization_id'], case['distractor_organization_id'])
        }
        orgs = {}
        for external_id in sorted(organization_ids):
            mapping = Phase11SeedMap.objects.filter(kind=f'{prefix}organization', external_id=external_id).first()
            org = Organization.objects.filter(pk=mapping.target_id).first() if mapping else None
            if org is None:
                org, _ = Organization.objects.get_or_create(name=f'Phase11 Eval {external_id}', defaults={'admin': user})
                Phase11SeedMap.objects.get_or_create(
                    kind=f'{prefix}organization', external_id=external_id,
                    defaults={'target_id': org.id, 'source_sha256': source_hash},
                )
            OrgUser.objects.get_or_create(org=org, user=user, defaults={'role': 'admin'})
            orgs[external_id] = org
        seen = set()
        for case in cases:
            for org_key, evidence_ids in ((case['authorized_organization_id'], case['authorized_user_evidence_ids']), (case['distractor_organization_id'], case['forbidden_user_evidence_ids'])):
                for external_id in evidence_ids:
                    if external_id in seen:
                        continue
                    seen.add(external_id)
                    if Phase11SeedMap.objects.filter(kind=f'{prefix}user_evidence', external_id=external_id).exists():
                        continue
                    binding = bindings.get(external_id)
                    if binding is None:
                        raise CommandError(f'missing_source_binding:{external_id}')
                    source_id = Phase11SeedMap.objects.filter(
                        kind=f'{prefix}user_evidence', external_id=binding['source_user_evidence_id'],
                    ).values_list('target_id', flat=True).first()
                    source = UserEvidence.objects.select_related('chunk__resource').filter(pk=source_id).first()
                    if source is None:
                        raise CommandError(f'missing_source_evidence:{binding["source_user_evidence_id"]}')
                    resource = create_resource_with_chunks(
                        type_=source.resource.source_type, title=source.resource.display_name,
                        source_url=source.resource.source_url, full_text=source.chunk.text,
                        organization_id=str(orgs[org_key].id), knowledge_domain='user_evidence',
                    )
                    evidence = UserEvidence.objects.create(resource=resource, chunk=resource.chunks.order_by('id').first(), organization_id=str(orgs[org_key].id), controlled_summary='phase11_cross_org_fixture')
                    Phase11SeedMap.objects.get_or_create(kind=f'{prefix}user_evidence', external_id=external_id, defaults={'target_id': evidence.id, 'source_sha256': source_hash})
        self.stdout.write(self.style.SUCCESS(f'phase11_cross_org_seeds_imported: organizations={len(orgs)} evidence={len(seen)}'))
