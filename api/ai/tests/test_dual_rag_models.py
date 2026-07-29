from django.core.exceptions import ValidationError
from django.test import TestCase

from ai.ingestion import create_resource_with_chunks
from ai.models import AIChunk, AIResource, ClaimEvidenceBinding, GrantPack, GrantProgram, UserEvidence


class DualRagModelTests(TestCase):
    def test_grant_rule_requires_pack_or_pack_draft(self):
        resource = AIResource(
            source_type='guideline',
            sha256='a' * 64,
            knowledge_domain='grant_rule',
            classification_status='classified',
        )
        with self.assertRaises(ValidationError):
            resource.clean()

        resource.classification_status = 'pack_draft'
        resource.clean()

        program = GrantProgram.objects.create(name='NSFC', program_type='youth', authority='NSFC')
        pack = GrantPack.objects.create(program=program, code='nsfc-youth', name='NSFC Youth')
        resource.classification_status = 'classified'
        resource.grant_pack = pack
        resource.clean()

    def test_chunk_domain_and_namespace_must_match_resource(self):
        resource = create_resource_with_chunks(
            type_='guideline',
            title='Guide',
            source_url='',
            full_text='Rule text.',
        )
        AIResource.objects.filter(pk=resource.pk).update(
            knowledge_domain='grant_rule',
            classification_status='pack_draft',
        )
        resource.refresh_from_db()
        chunk = resource.chunks.get()
        chunk.knowledge_domain = 'grant_rule'
        chunk.index_namespace = 'user_evidence'
        with self.assertRaises(ValidationError):
            chunk.clean()

        chunk.index_namespace = 'grant_rule'
        chunk.clean()

    def test_user_evidence_and_claim_binding_keep_domain_boundaries(self):
        resource = create_resource_with_chunks(
            type_='team_profile',
            title='Team',
            source_url='',
            full_text='Team publication evidence.',
            organization_id='org-a',
        )
        AIResource.objects.filter(pk=resource.pk).update(
            knowledge_domain='user_evidence',
            classification_status='classified',
        )
        resource.refresh_from_db()
        chunk = resource.chunks.get()
        AIChunk.objects.filter(pk=chunk.pk).update(
            knowledge_domain='user_evidence',
            index_namespace='user_evidence',
        )
        chunk.refresh_from_db()
        evidence = UserEvidence(resource=resource, chunk=chunk, organization_id='org-a')
        evidence.clean()

        binding = ClaimEvidenceBinding()
        with self.assertRaises(ValidationError):
            binding.clean()
