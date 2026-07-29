import hashlib
import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ai.ingestion import create_resource_with_chunks
from ai.models import EvidenceFact, GrantPack, GrantPackVersion, GrantProgram, GrantRequirement, Phase11SeedMap, UserEvidence
from orgs.models import Organization, OrgUser
from proposals.models import Proposal


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


class Command(BaseCommand):
    help = 'Import verified Phase 11 data as isolated evaluation fixtures and create external ID mappings.'

    def add_arguments(self, parser):
        parser.add_argument('--input-dir', required=True)
        parser.add_argument('--user-id', required=True, type=int)
        parser.add_argument('--mapping-kind-prefix', default='')

    @transaction.atomic
    def handle(self, *args, **options):
        root = Path(options['input_dir'])
        mapping_kind_prefix = options['mapping_kind_prefix']
        manifest = json.loads((root / 'phase11_external_id_seed_manifest.json').read_text(encoding='utf-8'))
        user = get_user_model().objects.filter(pk=options['user_id']).first()
        if user is None:
            raise CommandError('seed_owner_not_found')
        source_hash = digest(manifest)
        def mapped(kind, external_id, target):
            kind = f'{mapping_kind_prefix}{kind}'
            row, created = Phase11SeedMap.objects.get_or_create(kind=kind, external_id=external_id, defaults={'target_id': target.id, 'source_sha256': source_hash})
            if not created and row.target_id != target.id:
                raise CommandError(f'seed_mapping_conflict:{kind}:{external_id}')
            return target
        packs = {}
        for item in manifest['grant_pack_versions']:
            program, _ = GrantProgram.objects.get_or_create(name=item['family'], program_type='phase11_eval', region=item['region'], defaults={'authority': 'phase11_eval_fixture'})
            pack, _ = GrantPack.objects.get_or_create(code=item['external_id'], defaults={'program': program, 'name': item['family'], 'is_public': False})
            version, _ = GrantPackVersion.objects.get_or_create(pack=pack, year=item['applicable_year'], version='phase11', defaults={'status': 'published'})
            packs[item['external_id']] = mapped('grant_pack_version', item['external_id'], version)
        for item in manifest['grant_requirements']:
            version = packs[item['grant_pack_version_external_id']]
            answer = str(item.get('reference_answer') or item['rule_query'])
            resource = create_resource_with_chunks(type_='guideline', title=f"Phase11 {item['external_id']}", source_url='', full_text=f"{item['rule_query']}\n{answer}", knowledge_domain='grant_rule')
            resource.grant_pack = version.pack; resource.classification_status = 'classified'; resource.metadata = {'phase11_eval_fixture': True, 'external_id': item['external_id']}; resource.save(update_fields=['grant_pack', 'classification_status', 'metadata'])
            requirement = GrantRequirement.objects.create(pack_version=version, source_chunk=resource.chunks.order_by('id').first(), requirement_type='content', mandatory=True, text=answer, source_excerpt=answer, applicability={'year': item['applicable_year'], 'program_type': item['program_type'], 'region': item['region']})
            mapped('grant_requirement', item['external_id'], requirement)
        orgs, proposals = {}, {}
        for item in manifest['user_evidences']:
            org_key = item['organization_external_id']; proposal_key = item['proposal_external_id']
            if org_key not in orgs:
                org, _ = Organization.objects.get_or_create(name=f'Phase11 Eval {org_key}', defaults={'admin': user}); OrgUser.objects.get_or_create(org=org, user=user, defaults={'role': 'admin'}); orgs[org_key] = mapped('organization', org_key, org)
            if proposal_key not in proposals:
                proposal = Proposal.objects.create(author=user, org=orgs[org_key], content={'meta': {'title': proposal_key, 'phase11_eval_fixture': True}}); proposals[proposal_key] = mapped('proposal', proposal_key, proposal)
            text = item.get('document_text') or (
                f"{item['query']}\nrole={item['expected_role']}\n"
                f"value={item['expected_numeric_value']}\nstatus={item['expected_fact_status']}"
            )
            resource = create_resource_with_chunks(type_='team_profile', title=f"Phase11 {item['external_id']}", source_url='', full_text=text, organization_id=str(orgs[org_key].id), proposal_id=proposals[proposal_key].id, knowledge_domain='user_evidence')
            evidence = UserEvidence.objects.create(resource=resource, chunk=resource.chunks.order_by('id').first(), organization_id=str(orgs[org_key].id), proposal=proposals[proposal_key], controlled_summary='phase11_eval_fixture')
            EvidenceFact.objects.create(user_evidence=evidence, subject='phase11_eval_fixture', predicate=item['expected_role'], object=item['query'], fact_type='phase11', numeric_value=item['expected_numeric_value'], fact_status='planned' if item['expected_fact_status'] == 'planned' else 'completed', verification_status='user_confirmed')
            mapped('user_evidence', item['external_id'], evidence)
        self.stdout.write(self.style.SUCCESS(f'phase11_verified_seeds_imported: packs={len(packs)} requirements={len(manifest["grant_requirements"])} evidence={len(manifest["user_evidences"])}'))
