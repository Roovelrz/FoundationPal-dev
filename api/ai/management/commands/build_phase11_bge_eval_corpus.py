import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ai.embedding_service import EmbeddingService
from ai.domain_indexing import _input_hash, _token_count, context_prefix
from ai.models import AIChunk, AIResource, EvidenceFact, GrantPack, GrantPackVersion, GrantProgram, GrantRequirement, Phase11SeedMap, UserEvidence
from orgs.models import Organization, OrgUser
from proposals.models import Proposal


MAP_PREFIX = 'phase11_bge_'
PARSER_VERSION = 'phase40-p0-rule-corpus-v4'


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def _normalized(value):
    return ''.join(value.lower().split())


class Command(BaseCommand):
    help = 'Build an isolated BGE Phase 11 corpus from original frozen-set gold chunks without copying test queries.'

    def add_arguments(self, parser):
        parser.add_argument('--input-dir', required=True)
        parser.add_argument('--user-id', required=True, type=int)
        parser.add_argument('--model-path', required=True)
        parser.add_argument('--output', default='reports/phase11-bge-corpus-readiness.json')
        parser.add_argument('--binding-file', default='')
        parser.add_argument('--allow-synthetic-test-fixtures', action='store_true')
        parser.add_argument('--mapping-kind-prefix', default=MAP_PREFIX)

    def _map(self, kind, external_id, target, source_hash):
        record, created = Phase11SeedMap.objects.get_or_create(
            kind=f'{self.mapping_kind_prefix}{kind}', external_id=external_id,
            defaults={'target_id': target.id, 'source_sha256': source_hash},
        )
        if not created and record.target_id != target.id:
            raise CommandError(f'bge_seed_mapping_conflict:{kind}:{external_id}')
        return target

    def _original_chunk(self, chunk_id):
        return AIChunk.objects.select_related('resource').filter(pk=chunk_id).first()

    def _clone_source(self, source, *, domain, organization_id='', proposal_id=None):
        source_hash = hashlib.sha256(f'{domain}:{source.id}:{organization_id}:{proposal_id or ""}'.encode('utf-8')).hexdigest()
        resource, _ = AIResource.objects.get_or_create(
            organization_id=organization_id, sha256=source_hash, parser_version=PARSER_VERSION,
            defaults={
                'proposal_id': proposal_id,
                'source_type': 'guideline' if domain == 'grant_rule' else 'team_profile',
                'evidence_purpose': 'constraint' if domain == 'grant_rule' else 'fact',
                'knowledge_domain': domain,
                'classification_status': 'pack_draft' if domain == 'grant_rule' else 'classified',
                'title': f'Phase11 BGE source {source.id}',
                'display_name': source.resource.display_name or f'Phase11 BGE source {source.id}',
                'mime_type': source.resource.mime_type or 'text/plain',
                'source_url': source.resource.source_url,
                'page_count': 1,
                'metadata': {
                    'phase11_bge_eval': True,
                    'original_chunk_id': source.id,
                    'original_resource_id': source.resource_id,
                    'source_display_name': source.resource.display_name,
                    'source_file_name': source.resource.display_name,
                    'source_file_sha256': source.resource.sha256,
                    'source_page_start': source.page_start,
                    'source_page_end': source.page_end,
                    'source_url': source.resource.source_url,
                },
            },
        )
        chunk = resource.chunks.order_by('id').first()
        if chunk is None:
            text_hash = hashlib.sha256(source.text.encode('utf-8')).hexdigest()
            chunk = AIChunk.objects.create(
                resource=resource, knowledge_domain=domain,
                chunk_type='requirement' if domain == 'grant_rule' else 'team_profile',
                index_namespace=domain, index_version=PARSER_VERSION,
                stable_chunk_id=hashlib.sha256(f'{source_hash}:{text_hash}'.encode('utf-8')).hexdigest(),
                chunk_index=0, text=source.text, normalized_text=source.text,
                text_sha256=text_hash, page_start=source.page_start, page_end=source.page_end,
                section_title=source.section_title, heading_path=source.heading_path,
                token_count=_token_count(source.text), metadata={'phase11_bge_eval': True},
            )
        return resource, chunk

    def _embed_pending(self, service, chunks):
        unique = {chunk.id: chunk for chunk in chunks}
        values = list(unique.values())
        for start in range(0, len(values), 32):
            batch = values[start:start + 32]
            inputs = []
            for chunk in batch:
                prefix = context_prefix(
                    resource=chunk.resource, knowledge_domain=chunk.knowledge_domain,
                    chunk_type=chunk.chunk_type, section_path=chunk.section_path or chunk.heading_path,
                )
                inputs.append(f'{prefix}\n\n{chunk.text}')
            vectors = service.embed(inputs)
            for chunk, embedding, embedding_input in zip(batch, vectors, inputs):
                chunk.embedding = embedding
                chunk.embedding_model = service.model_name
                chunk.embedding_dimension = service.dim
                chunk.embedding_input_hash = _input_hash(embedding_input)
                chunk.embedding_key = _input_hash(f'{chunk.embedding_input_hash}:{service.dim}')
                chunk.metadata = {**(chunk.metadata or {}), 'context_prefix': embedding_input.split('\n\n', 1)[0]}
            AIChunk.objects.bulk_update(
                batch,
                ['embedding', 'embedding_model', 'embedding_dimension', 'embedding_input_hash', 'embedding_key', 'metadata'],
            )
        AIResource.objects.filter(pk__in={chunk.resource_id for chunk in values}).update(
            embedding_model=service.model_name, embedding_revision=service.model_revision, embedding_dimension=service.dim,
        )

    @transaction.atomic
    def handle(self, *args, **options):
        os.environ['EMBEDDING_BACKEND'] = 'bge'
        os.environ['BGE_MODEL_PATH'] = options['model_path']
        EmbeddingService.reset()
        service = EmbeddingService.instance()
        if service.backend != 'bge':
            raise CommandError('real_embedding_backend_required')
        root = Path(options['input_dir'])
        self.mapping_kind_prefix = options['mapping_kind_prefix']
        user = get_user_model().objects.filter(pk=options['user_id']).first()
        if user is None:
            raise CommandError('seed_owner_not_found')
        files = {
            'rules': json.loads((root / '01_rule_requirement_mapping.json').read_text(encoding='utf-8'))['cases'],
            'evidence': json.loads((root / '02_user_evidence_grounding.json').read_text(encoding='utf-8'))['cases'],
            'mixed': json.loads((root / '04_mixed_dual_domain.json').read_text(encoding='utf-8'))['cases'],
        }
        source_hash = _digest(files)
        rule_bindings = {}
        evidence_bindings = {}
        manual_evidence_bindings = set()
        for row in files['rules']:
            for external_id, chunk_id in zip(row['requirement_ids'], row['gold_chunk_ids']):
                existing = rule_bindings.setdefault(external_id, chunk_id)
                if existing != chunk_id:
                    raise CommandError(f'conflicting_rule_gold_chunk:{external_id}')
        pack_scopes = {}
        for row in files['rules']:
            scope = pack_scopes.setdefault(row['grant_pack_version_id'], {'phase11_bge_eval': True})
            for key in ('year', 'program_type', 'region'):
                value = row['applicable_year'] if key == 'year' else row[key]
                scope.setdefault(key, set()).add(value)
        pack_scopes = {
            key: {field: sorted(values) if isinstance(values, set) else values for field, values in scope.items()}
            for key, scope in pack_scopes.items()
        }
        for row in files['evidence'] + files['mixed']:
            evidence_ids = row.get('user_evidence_ids', [])
            chunks = row.get('gold_chunk_ids', [])
            if not chunks:
                manual_evidence_bindings.update(evidence_ids)
                continue
            for index, external_id in enumerate(evidence_ids):
                chunk_id = chunks[min(index, len(chunks) - 1)]
                existing = evidence_bindings.setdefault(external_id, chunk_id)
                if existing != chunk_id:
                    manual_evidence_bindings.add(external_id)
        manual_evidence_bindings.difference_update(evidence_bindings)
        binding_path = Path(options['binding_file']) if options['binding_file'] else root / 'phase11_original_evidence_bindings.json'
        if binding_path.exists():
            binding_cases = json.loads(binding_path.read_text(encoding='utf-8')).get('cases', [])
            for binding in binding_cases:
                accepted_statuses = {'human_confirmed'}
                if options['allow_synthetic_test_fixtures']:
                    accepted_statuses.add('synthetic_test_confirmed')
                if binding.get('status') not in accepted_statuses:
                    continue
                required = ('external_id', 'stable_chunk_id', 'page_start', 'organization_id', 'authorization_scope', 'reviewer', 'review_date')
                if any(binding.get(key) in (None, '') for key in required):
                    raise CommandError(f'incomplete_original_evidence_binding:{binding.get("external_id", "unknown")}')
                source = AIChunk.objects.select_related('resource').filter(stable_chunk_id=binding['stable_chunk_id']).first()
                if source is None or source.knowledge_domain != 'user_evidence':
                    raise CommandError(f'original_evidence_chunk_not_found:{binding["external_id"]}')
                if source.page_start != binding['page_start'] or source.page_end != binding.get('page_end', source.page_end):
                    raise CommandError(f'original_evidence_page_mismatch:{binding["external_id"]}')
                if source.resource.organization_id != binding['organization_id'] or source.resource.proposal_id != binding.get('proposal_id'):
                    raise CommandError(f'original_evidence_scope_mismatch:{binding["external_id"]}')
                evidence_bindings[binding['external_id']] = source.id
                manual_evidence_bindings.discard(binding['external_id'])

        pack_cache = {}
        resource_cache = {}
        org_cache = {}
        proposal_cache = {}
        rule_created = evidence_created = 0
        rule_corpus_chunk_ids = set()
        missing_rule_chunks = []
        missing_evidence_chunks = []
        query_leaks = []
        pending_chunks = []

        for row in files['rules']:
            pack_external_id = row['grant_pack_version_id']
            if pack_external_id not in pack_cache:
                program, _ = GrantProgram.objects.get_or_create(
                    name=f'Phase11 BGE Eval {pack_external_id}', program_type=row['program_type'], region=row['region'],
                    defaults={'authority': 'phase11_bge_eval'},
                )
                pack, _ = GrantPack.objects.get_or_create(
                    code=f'phase11-bge-{pack_external_id}', defaults={'program': program, 'name': program.name, 'is_public': False},
                )
                version, _ = GrantPackVersion.objects.get_or_create(
                    pack=pack, year=row['applicable_year'], version=PARSER_VERSION,
                    defaults={'status': 'published', 'detected_metadata': {'phase11_bge_eval': True}},
                )
                pack_cache[pack_external_id] = self._map('grant_pack_version', pack_external_id, version, source_hash)
            version = pack_cache[pack_external_id]
            for external_id, chunk_id in zip(row['requirement_ids'], row['gold_chunk_ids']):
                source = self._original_chunk(chunk_id)
                if source is None:
                    missing_rule_chunks.append({'external_id': external_id, 'gold_chunk_id': chunk_id})
                    continue
                requirement = None
                for original_chunk in source.resource.chunks.order_by('chunk_index', 'id'):
                    if original_chunk.id not in resource_cache:
                        resource_cache[original_chunk.id] = self._clone_source(original_chunk, domain='grant_rule')
                    resource, cloned_chunk = resource_cache[original_chunk.id]
                    pending_chunks.append(cloned_chunk)
                    applicability = {
                        'year': row['applicable_year'], 'program_type': row['program_type'],
                        'region': row['region'], 'phase11_bge_eval': True,
                    } if original_chunk.id == chunk_id else pack_scopes[pack_external_id]
                    candidate, _ = GrantRequirement.objects.get_or_create(
                        pack_version=version, source_chunk=cloned_chunk, text=original_chunk.text,
                        applicability=applicability,
                        defaults={
                            'requirement_type': 'content', 'mandatory': True, 'source_excerpt': original_chunk.text,
                        },
                    )
                    rule_corpus_chunk_ids.add(original_chunk.id)
                    if original_chunk.id == chunk_id:
                        requirement = candidate
                if requirement is None:
                    missing_rule_chunks.append({'external_id': external_id, 'gold_chunk_id': chunk_id})
                    continue
                self._map('grant_requirement', external_id, requirement, source_hash)
                rule_created += 1
                if _normalized(row['query']) in _normalized(source.text):
                    query_leaks.append({'domain': 'rule', 'case_id': row['case_id'], 'gold_chunk_id': chunk_id})

        evidence_rows = files['evidence'] + files['mixed']
        evidence_metadata = {}
        for row in evidence_rows:
            for external_id in row.get('user_evidence_ids', []):
                evidence_metadata.setdefault(external_id, row)
        for external_id, chunk_id in evidence_bindings.items():
            row = evidence_metadata[external_id]
            source = self._original_chunk(chunk_id)
            if source is None:
                missing_evidence_chunks.append({'external_id': external_id, 'gold_chunk_id': chunk_id})
                continue
            org_external_id = row['organization_id']
            if org_external_id not in org_cache:
                org, _ = Organization.objects.get_or_create(name=f'Phase11 BGE Eval {org_external_id}', defaults={'admin': user})
                OrgUser.objects.get_or_create(org=org, user=user, defaults={'role': 'admin'})
                org_cache[org_external_id] = self._map('organization', org_external_id, org, source_hash)
            org = org_cache[org_external_id]
            proposal_external_id = row.get('proposal_id') or f'phase11-bge-{org_external_id}'
            proposal_key = f'{org_external_id}:{proposal_external_id}'
            if proposal_key not in proposal_cache:
                existing = Phase11SeedMap.objects.filter(kind=f'{self.mapping_kind_prefix}proposal', external_id=proposal_external_id).first()
                if existing:
                    proposal = Proposal.objects.get(pk=existing.target_id)
                else:
                    proposal = Proposal.objects.create(author=user, org=org, content={'meta': {'phase11_bge_eval': True, 'external_id': proposal_external_id}})
                    self._map('proposal', proposal_external_id, proposal, source_hash)
                proposal_cache[proposal_key] = proposal
            proposal = proposal_cache[proposal_key]
            resource, cloned_chunk = self._clone_source(
                source, domain='user_evidence', organization_id=str(org.id), proposal_id=proposal.id,
            )
            pending_chunks.append(cloned_chunk)
            evidence, _ = UserEvidence.objects.get_or_create(
                resource=resource, chunk=cloned_chunk, organization_id=str(org.id), proposal=proposal,
                defaults={'controlled_summary': 'phase11_bge_original_gold_chunk'},
            )
            EvidenceFact.objects.get_or_create(
                user_evidence=evidence, subject='phase11_bge_original_gold_chunk', predicate='source_fact', object=source.text[:1000],
                defaults={'fact_type': 'phase11_bge_eval', 'fact_status': 'completed', 'verification_status': 'user_confirmed'},
            )
            self._map('user_evidence', external_id, evidence, source_hash)
            evidence_created += 1
            if row['query'] in source.text:
                query_leaks.append({'domain': 'user_evidence', 'case_id': row['case_id'], 'gold_chunk_id': chunk_id})

        self._embed_pending(service, pending_chunks)

        rule_query_leaks = [item for item in query_leaks if item['domain'] == 'rule']
        payload = {
            'corpus_version': PARSER_VERSION,
            'embedding': service.health(),
            'rule_requirement_mappings': len(rule_bindings),
            'rule_requirement_seed_operations': rule_created,
            'rule_corpus_original_chunk_count': len(rule_corpus_chunk_ids),
            'rule_corpus_gold_chunk_count': len({chunk_id for chunk_id in rule_bindings.values()}),
            'rule_corpus_non_gold_chunk_count': len(rule_corpus_chunk_ids - set(rule_bindings.values())),
            'evidence_mappings_from_original_gold_chunks': len(evidence_bindings),
            'evidence_seed_operations': evidence_created,
            'manual_evidence_source_binding_external_ids': sorted(manual_evidence_bindings),
            'original_evidence_binding_file': str(binding_path) if binding_path.exists() else None,
            'synthetic_test_fixture_count': sum(1 for item in binding_cases if item.get('status') == 'synthetic_test_confirmed') if binding_path.exists() else 0,
            'missing_rule_chunks': missing_rule_chunks,
            'missing_evidence_chunks': missing_evidence_chunks,
            'query_leak_observations': query_leaks,
            'rule_query_leak_observations': rule_query_leaks,
            'semantic_baseline_status': 'ready_for_rule_only_bge_eval' if not missing_rule_chunks and not rule_query_leaks else 'manual_review_required',
            'user_evidence_semantic_baseline_status': 'blocked_by_missing_original_gold_chunk_bindings' if manual_evidence_bindings else ('ready_synthetic_test_fixture' if any(item.get('status') == 'synthetic_test_confirmed' for item in binding_cases) else 'ready'),
        }
        output = Path(options['output'])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS('phase11_bge_eval_corpus_ready'))
